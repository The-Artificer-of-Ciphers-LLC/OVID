with open("api/tests/test_auth_mastodon.py", "r") as f:
    code = f.read()

code = code.replace("""        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }""", """        mock_resp = httpx.Response(200, json={
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }, request=httpx.Request("POST", "https://mastodon.example.com"))""")

code = code.replace("""        mock_token_resp = AsyncMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "test_access_token"}""", """        mock_token_resp = httpx.Response(200, json={"access_token": "test_access_token"}, request=httpx.Request("POST", "url"))""")

code = code.replace("""        mock_verify_resp = AsyncMock()
        mock_verify_resp.status_code = 200
        mock_verify_resp.json.return_value = {
            "id": "12345",
            "username": "testuser",
            "display_name": "Test User"
        }""", """        mock_verify_resp = httpx.Response(200, json={
            "id": "12345",
            "username": "testuser",
            "display_name": "Test User"
        }, request=httpx.Request("GET", "url"))""")

with open("api/tests/test_auth_mastodon.py", "w") as f:
    f.write(code)
