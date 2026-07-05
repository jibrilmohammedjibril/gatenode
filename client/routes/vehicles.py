from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.db import get_db
from core.models import User, Vehicle, VehicleStatus, generate_access_code
from core.deps import get_current_user, get_current_unit, require_estate_membership
from schemas import VehicleCreate, VehicleResponse, StickerFeeResponse

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])

@router.get("/sticker-fee", response_model=StickerFeeResponse)
async def get_sticker_fee(
    unitId: str = None, 
    destination_state: str = "Lagos", # Default to Lagos if not provided
    current_user: User = Depends(get_current_user)
):
    """Return the cost for a new vehicle sticker."""
    base_amount = 1000
    fee = None 

    # Try Fez Delivery
    from core.fez_delivery import get_fez_delivery_cost
    
    # Assume Estate is in Lagos for now (or fetch from DB if Estate model has state)
    origin_state = "Lagos" 
    
    try:
        cost_data = await get_fez_delivery_cost(destination_state, origin_state)
        if cost_data:
            fee = int(cost_data['cost'])
        else:
             raise Exception("No cost returned from provider.")
    except Exception as e:
        print(f"Delivery Fee Error: {e}")
        # Request change: Return error if not available, do not default.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Unable to calculate delivery fee for the specified location. Please try again or contact support."
        )

    return {
        "amount": base_amount, 
        "currency": "NGN",
        "deliveryFee": fee, 
        "total": base_amount + fee 
    }

@router.post("", response_model=VehicleResponse)
async def register_vehicle(
    data: VehicleCreate,
    current_user: User = Depends(require_estate_membership()),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    # Check if plate exists
    exists = await db.execute(select(Vehicle).where(Vehicle.plate_number == data.plateNumber))
    if exists.scalars().first():
        raise HTTPException(status_code=400, detail="Vehicle with this plate already registered")
        
    new_vehicle = Vehicle(
        make=data.make,
        model=data.model,
        plate_number=data.plateNumber, # Map camelCase to snake_case
        color=data.color,
        status=VehicleStatus.PENDING_DELIVERY, 
        user_id=current_user.id,
        estate_id=current_user.estate_id,
        unit_id=unit.id if unit else None
        # payment_reference removed from create payload in spec, confusing? 
        # Checking spec: request body has no paymentRef. 
        # Maybe free registration or separate payment flow? 
        # We'll ignore payment ref for now unless needed.
    )
    
    db.add(new_vehicle)
    await db.commit()
    await db.refresh(new_vehicle)
    
    return {
        "id": new_vehicle.id,
        "make": new_vehicle.make,
        "model": new_vehicle.model,
        "plateNumber": new_vehicle.plate_number,
        "color": new_vehicle.color,
        "status": new_vehicle.status,
        "qrCodeData": new_vehicle.qr_code_data
    }

@router.delete("/{vehicle_id}")
async def delete_vehicle(
    vehicle_id: str,
    current_user: User = Depends(require_estate_membership()),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.user_id == current_user.id)
    )
    vehicle = result.scalars().first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
        
    await db.delete(vehicle)
    await db.commit()
    return {"message": "Vehicle removed successfully"}

@router.get("", response_model=list[VehicleResponse])
async def list_my_vehicles(
    current_user: User = Depends(require_estate_membership()),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    query = select(Vehicle).where(Vehicle.user_id == current_user.id)
    
    if unit:
        query = query.where(Vehicle.unit_id == unit.id)
        
    result = await db.execute(query)
    vehicles = result.scalars().all()
    
    return [
        {
            "id": v.id,
            "make": v.make,
            "model": v.model,
            "plateNumber": v.plate_number,
            "color": v.color,
            "status": v.status,
            "qrCodeData": v.qr_code_data
        }
        for v in vehicles
    ]
