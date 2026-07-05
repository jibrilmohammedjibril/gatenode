import re

# Basic profanity list (can be expanded)
PROFANITY_WORDS = {
    "shit", "fuck", "bastard", "bitch", "asshole", "cunt", "piss", "dick",
    "crap", "damn", "motherfucker", "hell"
}

def mask_profanity(text: str) -> str:
    """
    Masks bad words with asterisks while maintaining word length.
    E.g. "shit" -> "****"
    """
    if not text:
        return text
        
    words = text.split()
    masked_words = []
    
    for word in words:
        # Strip punctuation for check
        clean_word = re.sub(r'[^\w\s]', '', word).lower()
        if clean_word in PROFANITY_WORDS:
            # Mask the original word (maintains its punctuation/case if needed)
            # but here we just replace the letters with *
            masked_words.append("*" * len(word))
        else:
            masked_words.append(word)
            
    return " ".join(masked_words)
