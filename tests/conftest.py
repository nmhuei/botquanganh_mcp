import os

# Disable security policy bypass during tests so security validations are executed and tested
os.environ["DISABLE_SECURITY_POLICIES"] = "false"
