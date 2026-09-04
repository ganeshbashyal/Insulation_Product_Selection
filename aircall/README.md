# Aircall trial pack

This directory is generated from the validated family catalogues and structured performance-evidence registry. Do not maintain its product claims separately.

## Trial setup

1. In Aircall, add `aircall_knowledge_base.txt` as a pasted **Block of content**.
2. Copy `aircall_agent_instructions.txt` into the agent goal/conversation guidance area.
3. Configure the four questions in `aircall_intake_questions.txt` as the intake flow.
4. Test unpublished/draft changes before attaching the agent to a live number.

The knowledge file includes supported product families and a small recognition-only list for blocked identities. Blocked products must never be recommended.

Rebuild after an approved catalogue or evidence change:

```powershell
python scripts/build_aircall_pack.py
python scripts/validate_aircall_pack.py
```

The manifest records the combined SHA-256 hash of the source family catalogues and performance-evidence registry. The generated pack is intentionally well below Aircall’s documented 300,000-character context threshold.
