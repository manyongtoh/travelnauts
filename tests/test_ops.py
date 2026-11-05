from brain.environments import check


def test_test_environment_defaults_pass():
    assert check("test", {"BRAIN_DATA_STAGE": "synthetic"}).ok


def test_pilot_refuses_writes_sandbox_sign_in_and_stand_in_model():
    c = check("pilot", {"BRAIN_DATA_STAGE": "anonymised", "BRAIN_TRAVELSPIRIT_WRITE": "drafts", "BRAIN_AUTH": "sandbox"})
    assert not c.ok and len(c.problems) == 3


def test_live_refuses_a_test_key_vault_and_database():
    c = check("live", {"BRAIN_DATA_STAGE": "live", "BRAIN_TRAVELSPIRIT_WRITE": "drafts", "BRAIN_AUTH": "entra",
                       "BRAIN_MODEL": "openai:gpt-4o", "AZURE_KEYVAULT_NAME": "kv-brain-test",
                       "BRAIN_DATABASE_URL": "postgresql://x@pg-brain-test/brain"})
    assert not c.ok and any("Key Vault" in p for p in c.problems) and any("Database" in p for p in c.problems)
