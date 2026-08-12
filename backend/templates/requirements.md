# Fax intake requirements

## Required fields
- patient_name: Full legal name
- date_of_birth: YYYY-MM-DD
- phone_number: E.164 if possible
- referring_physician: Name
- reason_for_referral: Free text
- insurance_id: Optional but preferred

## Contact rules
- Prefer phone_number from the fax for callback
- If phone missing but name present, do not invent a number
- Only call when at least one required field above is missing or low-confidence

## Call script goals
- Identify yourself as the clinic fax assistant
- Ask only for missing/low-confidence fields
- Confirm spelling of names and IDs
