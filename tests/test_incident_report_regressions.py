import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class IncidentRegressionTests(unittest.TestCase):
    def test_client_incident_route_uses_dedicated_endpoint_and_headers(self):
        source = (ROOT / "client/routes/incidents.py").read_text()
        self.assertIn('router = APIRouter(prefix="/incidents", tags=["Incidents"])', source)
        self.assertIn('@router.post("", response_model=IncidentResponse)', source)
        self.assertIn('x_estate_id: str = Header(..., alias="X-Estate-ID")', source)
        self.assertIn('x_tenant_id: str = Header(..., alias="X-Tenant-ID")', source)
        self.assertIn('x_unit_id: str = Header(..., alias="X-Unit-ID")', source)
        self.assertIn("SELECT nextval('incident_ticket_number_seq')", source)
        self.assertIn('return f"INC-{ticket_sequence:06d}"', source)

    def test_client_incident_schemas_match_mobile_contract(self):
        source = (ROOT / "client/schemas.py").read_text()
        self.assertIn("class IncidentCreate(BaseModel):", source)
        self.assertIn("category: str", source)
        self.assertIn('priority: Optional[str] = "high"', source)
        self.assertIn("attachments: List[str] = Field(default_factory=list)", source)
        self.assertIn("class IncidentResponse(BaseModel):", source)
        self.assertIn('ticket_number: str = Field(..., alias="ticketNumber")', source)
        self.assertIn('created_at: datetime = Field(..., alias="createdAt")', source)

    def test_client_docs_reference_dedicated_incidents_endpoint(self):
        source = (ROOT / "client/CLIENT_API_DOCUMENTATION.md").read_text()
        self.assertIn("- `/incidents`: submit resident incident reports", source)
        self.assertNotIn("POST /complaints/report-incident", source)

    def test_temporary_complaints_backed_incident_route_is_removed(self):
        source = (ROOT / "client/routes/complaints.py").read_text()
        self.assertNotIn("/report-incident", source)
        self.assertNotIn("IncidentReportResponse", source)


if __name__ == "__main__":
    unittest.main()
