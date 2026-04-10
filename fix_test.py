import re
with open("tests/test_api_server.py", "r") as f:
    code = f.read()

code = code.replace(', "state_store": "redis"', ', "state_store": "none"')
code = code.replace(', "metadata_store": "postgresql"', ', "metadata_store": "none"')

with open("tests/test_api_server.py", "w") as f:
    f.write(code)
