import uuid
from unittest.mock import patch


def _unique_slug(prefix: str = "tenant") -> str:
    """Genera un slug unico de organizacion para evitar colisiones entre tests."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _register(client, slug: str | None = None, email: str = "admin@example.com", password: str = "SecurePass123!"):
    slug = slug or _unique_slug()
    payload = {
        "tenant_name": "Empresa de Pruebas SAS",
        "tenant_slug": slug,
        "admin_email": email,
        "admin_password": password,
    }
    response = await client.post("/auth/register", json=payload)
    return response, slug


async def _login(client, email: str, password: str, tenant_slug: str | None = None):
    payload = {"email": email, "password": password}
    if tenant_slug:
        payload["tenant_slug"] = tenant_slug
    return await client.post("/auth/login", json=payload)


class TestAuth:
    async def test_register_creates_tenant_and_admin(self, client):
        """El registro debe crear el tenant y el usuario admin en una sola transaccion atomica."""
        response, slug = await _register(client)
        body = response.json()

        assert response.status_code == 201
        assert body["success"] is True
        assert body["data"]["tenant"]["slug"] == slug
        assert body["data"]["user"]["role"] == "admin"

    async def test_login_success_returns_access_token(self, client):
        """Un login exitoso debe retornar un access token en el cuerpo de la respuesta."""
        _, slug = await _register(client, email="user1@example.com", password="SecurePass123!")
        response = await _login(client, "user1@example.com", "SecurePass123!", slug)
        body = response.json()

        assert response.status_code == 200
        assert body["success"] is True
        assert "access_token" in body["data"]
        assert "refresh_token" in response.cookies

    async def test_login_wrong_password_returns_401(self, client):
        """Un login con contrasena incorrecta debe retornar 401."""
        _, slug = await _register(client, email="user2@example.com", password="SecurePass123!")
        response = await _login(client, "user2@example.com", "WrongPassword!", slug)

        assert response.status_code == 401
        assert response.json()["success"] is False

    async def test_protected_route_with_valid_token_returns_200(self, client):
        """El acceso a una ruta protegida (/auth/me) con un token valido debe retornar 200."""
        _, slug = await _register(client, email="user3@example.com", password="SecurePass123!")
        login_response = await _login(client, "user3@example.com", "SecurePass123!", slug)
        access_token = login_response.json()["data"]["access_token"]

        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        body = response.json()

        assert response.status_code == 200
        assert body["data"]["email"] == "user3@example.com"

    async def test_protected_route_without_token_returns_401(self, client):
        """El acceso a una ruta protegida sin token debe retornar 401."""
        response = await client.get("/auth/me")
        assert response.status_code == 401

    async def test_register_duplicate_slug_returns_error(self, client):
        """Registrar un tenant con un slug ya existente debe retornar un error."""
        _, slug = await _register(client, email="dupe1@example.com")
        response, _ = await _register(client, slug=slug, email="dupe2@example.com")

        assert response.status_code == 409
        assert response.json()["success"] is False

    async def test_refresh_and_logout_cycle(self, client):
        """Ciclo completo: login, refresh de token (rotacion) y logout invalidando la sesion."""
        _, slug = await _register(client, email="cycle@example.com", password="SecurePass123!")
        login_response = await _login(client, "cycle@example.com", "SecurePass123!", slug)
        assert "refresh_token" in login_response.cookies

        refresh_response = await client.post("/auth/refresh")
        refresh_body = refresh_response.json()
        assert refresh_response.status_code == 200
        assert "access_token" in refresh_body["data"]

        logout_response = await client.post("/auth/logout")
        assert logout_response.status_code == 200

        client.cookies.clear()
        post_logout_refresh = await client.post("/auth/refresh")
        assert post_logout_refresh.status_code == 401

    async def test_change_password_success_then_old_password_fails(self, client):
        """Cambiar la contrasena con la actual correcta debe funcionar; la vieja deja de servir."""
        _, slug = await _register(client, email="change-pw@example.com", password="OldPassword123!")
        login_response = await _login(client, "change-pw@example.com", "OldPassword123!", slug)
        headers = {"Authorization": f"Bearer {login_response.json()['data']['access_token']}"}

        response = await client.patch(
            "/auth/me/password",
            json={"current_password": "OldPassword123!", "new_password": "NewPassword456!"},
            headers=headers,
        )
        assert response.status_code == 200

        old_login = await _login(client, "change-pw@example.com", "OldPassword123!", slug)
        assert old_login.status_code == 401
        new_login = await _login(client, "change-pw@example.com", "NewPassword456!", slug)
        assert new_login.status_code == 200

    async def test_change_password_wrong_current_returns_401(self, client):
        """Cambiar la contrasena con la actual incorrecta debe retornar 401 y no modificarla."""
        _, slug = await _register(client, email="change-pw-wrong@example.com", password="OldPassword123!")
        login_response = await _login(client, "change-pw-wrong@example.com", "OldPassword123!", slug)
        headers = {"Authorization": f"Bearer {login_response.json()['data']['access_token']}"}

        response = await client.patch(
            "/auth/me/password",
            json={"current_password": "ContrasenaIncorrecta!", "new_password": "NewPassword456!"},
            headers=headers,
        )
        assert response.status_code == 401

        still_works = await _login(client, "change-pw-wrong@example.com", "OldPassword123!", slug)
        assert still_works.status_code == 200

    async def test_forgot_and_reset_password_flow(self, client):
        """Ciclo completo: pedir reset, usar el token para cambiar la contrasena, la vieja deja
        de servir y la nueva si. El token se mockea (secrets.token_urlsafe) porque el "envio de
        email" real es solo un log, no hay forma de leerlo desde el test."""
        _, slug = await _register(client, email="reset-user@example.com", password="OldPassword123!")

        with patch("app.services.auth_service.secrets.token_urlsafe", return_value="fixed-test-token"):
            forgot_response = await client.post(
                "/auth/forgot-password", json={"email": "reset-user@example.com", "tenant_slug": slug}
            )
        assert forgot_response.status_code == 200

        reset_response = await client.post(
            "/auth/reset-password", json={"token": "fixed-test-token", "new_password": "NewPassword456!"}
        )
        assert reset_response.status_code == 200

        old_login = await _login(client, "reset-user@example.com", "OldPassword123!", slug)
        assert old_login.status_code == 401
        new_login = await _login(client, "reset-user@example.com", "NewPassword456!", slug)
        assert new_login.status_code == 200

        # El token es de un solo uso: reutilizarlo debe fallar.
        reuse_response = await client.post(
            "/auth/reset-password", json={"token": "fixed-test-token", "new_password": "OtraClave789!"}
        )
        assert reuse_response.status_code == 400

    async def test_forgot_password_unknown_email_returns_200_generic(self, client):
        """No debe revelar si el email existe o no (previene enumeracion de usuarios): siempre 200."""
        response = await client.post(
            "/auth/forgot-password", json={"email": "no-existe-nunca@example.com", "tenant_slug": "cualquiera"}
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_reset_password_invalid_token_returns_400(self, client):
        """Un token invalido o inexistente debe retornar 400, no 200 ni 500."""
        response = await client.post(
            "/auth/reset-password", json={"token": "token-que-nunca-existio", "new_password": "NewPassword456!"}
        )
        assert response.status_code == 400
