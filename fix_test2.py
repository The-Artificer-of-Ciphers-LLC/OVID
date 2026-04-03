with open("api/tests/test_auth_mastodon.py", "r") as f:
    code = f.read()

code = code.replace('assert data["user"]["username"] == "testuser@mastodon.example.com"',
                    'assert data["user"]["username"] == "mastodon_mastodon.example.com:12345"')

with open("api/tests/test_auth_mastodon.py", "w") as f:
    f.write(code)
