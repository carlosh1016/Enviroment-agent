import uuid


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

    async def test_tenant_isolation_projects(self, client):
        """Un usuario del tenant A no debe poder acceder a proyectos del tenant B."""
        _, slug_a = await _register(client, email="admin_a@example.com", password="SecurePass123!")
        login_a = await _login(client, "admin_a@example.com", "SecurePass123!", slug_a)
        token_a = login_a.json()["data"]["access_token"]

        _, slug_b = await _register(client, email="admin_b@example.com", password="SecurePass123!")
        login_b = await _login(client, "admin_b@example.com", "SecurePass123!", slug_b)
        token_b = login_b.json()["data"]["access_token"]

        create_response = await client.post(
            "/projects/",
            json={"name": "Proyecto Tenant B"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        project_id = create_response.json()["data"]["id"]

        response = await client.get(
            f"/projects/{project_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )

        assert response.status_code == 404

    async def test_soft_delete_project_not_in_listing(self, client):
        """Un proyecto eliminado (soft delete) no debe aparecer en el listado de proyectos activos."""
        _, slug = await _register(client, email="deleter@example.com", password="SecurePass123!")
        login_response = await _login(client, "deleter@example.com", "SecurePass123!", slug)
        token = login_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        create_response = await client.post("/projects/", json={"name": "Proyecto a eliminar"}, headers=headers)
        project_id = create_response.json()["data"]["id"]

        delete_response = await client.delete(f"/projects/{project_id}", headers=headers)
        assert delete_response.status_code == 200

        list_response = await client.get("/projects/", headers=headers)
        ids = [item["id"] for item in list_response.json()["data"]["items"]]

        assert project_id not in ids
