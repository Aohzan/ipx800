"""Entry unload and stateless push routing regression tests."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import BasicAuth, web
from aiohttp.test_utils import TestClient, TestServer

from custom_components.ipx800v4 import (
    _async_remove_entry_data,
    async_setup,
    async_unload_entry,
)
from custom_components.ipx800v4.const import (
    CONF_DEVICES,
    COORDINATOR,
    DOMAIN,
    PUSH_CONFIG,
)
from custom_components.ipx800v4.push import (
    IpxRequestView,
    IpxRequestDataView,
    IpxRequestBulkUpdateView,
    IpxRequestRefreshView,
)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    """Keep the same HTTP views while replacing controller runtimes."""

    async def asyncSetUp(self):
        self.hass = SimpleNamespace(
            data={DOMAIN: {}},
            config_entries=SimpleNamespace(
                async_unload_platforms=AsyncMock(return_value=True)
            ),
            http=SimpleNamespace(register_view=Mock()),
            states=SimpleNamespace(
                get=Mock(return_value=SimpleNamespace(state="off", attributes={})),
                async_set=Mock(),
            ),
        )
        self.registry_entries = {}
        registry = SimpleNamespace(async_get=self.registry_entries.get)
        self.registry_patch = patch(
            "custom_components.ipx800v4.push.er.async_get", return_value=registry
        )
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)
        self.entries_patch = patch(
            "custom_components.ipx800v4.push.er.async_entries_for_config_entry",
            side_effect=lambda registry, entry_id: [
                entry for entry in self.registry_entries.values()
                if entry.config_entry_id == entry_id
            ],
        )
        self.entries_patch.start()
        self.addCleanup(self.entries_patch.stop)
        self.a = self.add_entry("a", "A", "secret-a")
        self.b = self.add_entry("b", "B", "secret-b")
        self.views = [
            IpxRequestView(), IpxRequestDataView(),
            IpxRequestBulkUpdateView(), IpxRequestRefreshView(),
        ]
        app = web.Application()
        app["hass"] = self.hass
        for view in self.views:
            async def handler(request, view=view):
                return await view.get(request, **request.match_info)
            for url in (view.url, *view.extra_urls):
                app.router.add_get(url, handler)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    def add_entry(self, entry_id, name, password):
        runtime = {
            "name": name,
            "controller": object(),
            COORDINATOR: SimpleNamespace(
                async_request_refresh=AsyncMock(), async_shutdown=AsyncMock(),
                config_entry=SimpleNamespace(entry_id=entry_id),
                push_entities={}, async_apply_push=Mock()
            ),
            CONF_DEVICES: {"switch": [{
                "component": "switch", "name": name + " relay",
                "type": "relay", "id": 1, "invert_value": False,
            }]},
            PUSH_CONFIG: {
                "name": name, "host": "127.0.0.1",
                "push_password": password, "push_check_host": True,
            },
        }
        entity_id = f"switch.{name.lower()}_relay"
        unique_id = entry_id + "_relay"
        entity = SimpleNamespace(
            entity_id=entity_id, _ipx_type="relay", _push_binary=True,
            _id=1, push_key="R1",
            push_values=lambda state: {"R1": int(state in ("on", "1"))},
        )
        runtime[COORDINATOR].push_entities[unique_id] = entity
        self.registry_entries[entity_id] = SimpleNamespace(
            entity_id=entity_id, unique_id=unique_id, platform=DOMAIN,
            config_entry_id=entry_id,
        )
        self.hass.data[DOMAIN][entry_id] = runtime
        return runtime

    async def get(self, url, password="secret-a"):
        response = await self.client.get(url, auth=BasicAuth("ipx800", password))
        await response.read()
        return response.status

    async def test_routes_registered_only_in_integration_setup(self):
        await async_setup(self.hass, {})
        self.assertEqual(self.hass.http.register_view.call_count, 4)
        await async_unload_entry(self.hass, SimpleNamespace(entry_id="a"))
        self.add_entry("a", "A", "new-password")
        self.assertEqual(self.hass.http.register_view.call_count, 4)

    async def test_reload_uses_current_coordinator_and_credentials(self):
        for index in range(3):
            old = self.hass.data[DOMAIN]["a"]
            self.assertTrue(await async_unload_entry(self.hass, SimpleNamespace(entry_id="a")))
            old[COORDINATOR].async_shutdown.assert_awaited_once()
            self.assertEqual(await self.get("/api/ipx800v4_refresh/A/on"), 401)
            password = f"new-{index}"
            current = self.add_entry("a", "A", password)
            self.assertEqual(await self.get("/api/ipx800v4_refresh/A/on"), 401)
            self.assertEqual(await self.get("/api/ipx800v4_refresh/A/on", password), 200)
            self.assertEqual(await self.get("/api/ipx800v4_refresh/on", password), 200)
            self.assertEqual(current[COORDINATOR].async_request_refresh.await_count, 2)
            # Neither the other runtime nor the views are replaced on reload.
            self.assertIs(self.hass.data[DOMAIN]["b"], self.b)
            self.assertEqual(await self.get("/api/ipx800v4_refresh/B/on", "secret-b"), 200)
            self.assertEqual(old[COORDINATOR].async_request_refresh.await_count, 0 if index == 0 else 2)

    async def test_all_endpoint_forms_resolve_current_runtime(self):
        await async_unload_entry(self.hass, SimpleNamespace(entry_id="a"))
        current = self.add_entry("a", "A", "replacement")
        for url in (
            "/api/ipx800v4/A/switch.a_relay/on",
            "/api/ipx800v4/switch.a_relay/on",
            "/api/ipx800v4_data/A/switch.a_relay=1",
            "/api/ipx800v4_data/switch.a_relay=1",
            "/api/ipx800v4_bulk/A/relay/1",
            "/api/ipx800v4_bulk/relay/1",
        ):
            with self.subTest(url=url):
                self.assertEqual(await self.get(url, "replacement"), 200)
                self.assertEqual(await self.get(url, "secret-a"), 401)
        self.hass.states.async_set.assert_not_called()
        self.assertEqual(current[COORDINATOR].async_apply_push.call_count, 6)
        current[COORDINATOR].async_request_refresh.assert_not_awaited()
        self.b[COORDINATOR].async_request_refresh.assert_not_awaited()

    async def test_bulk_uses_reloaded_device_list(self):
        await async_unload_entry(self.hass, SimpleNamespace(entry_id="a"))
        current = self.add_entry("a", "A", "secret-a")
        entity = current[COORDINATOR].push_entities["a_relay"]
        entity.entity_id = "switch.new_relay"
        entry = self.registry_entries.pop("switch.a_relay")
        entry.entity_id = entity.entity_id
        self.registry_entries[entity.entity_id] = entry
        self.assertEqual(await self.get("/api/ipx800v4_bulk/A/relay/1"), 200)
        current[COORDINATOR].async_apply_push.assert_called_once_with({"R1": 1})
        self.hass.states.async_set.assert_not_called()

    async def test_ambiguous_legacy_route_is_rejected(self):
        self.b[PUSH_CONFIG]["push_password"] = "secret-a"
        self.assertEqual(await self.get("/api/ipx800v4_refresh/on"), 401)
        self.assertEqual(await self.get("/api/ipx800v4_refresh/A/on"), 200)
        self.a[COORDINATOR].async_request_refresh.assert_awaited_once()
        self.b[COORDINATOR].async_request_refresh.assert_not_awaited()

    async def test_unknown_name_host_and_malformed_auth_are_rejected(self):
        self.assertEqual(await self.get("/api/ipx800v4_refresh/missing/on"), 401)
        self.a[PUSH_CONFIG]["host"] = "192.0.2.10"
        self.assertEqual(await self.get("/api/ipx800v4_refresh/A/on"), 401)
        for auth in ("", "Basic !!!", "Bearer token", "Basic bm9jb2xvbg=="):
            response = await self.client.get("/api/ipx800v4_refresh/A/on", headers={"Authorization": auth})
            self.assertEqual(response.status, 401)
            await response.read()
        self.a[COORDINATOR].async_request_refresh.assert_not_awaited()

    async def test_failed_unload_keeps_runtime_and_push_working(self):
        self.hass.config_entries.async_unload_platforms.return_value = False
        self.assertFalse(await async_unload_entry(self.hass, SimpleNamespace(entry_id="a")))
        self.assertIs(self.hass.data[DOMAIN]["a"], self.a)
        self.a[COORDINATOR].async_shutdown.assert_not_awaited()
        self.assertEqual(await self.get("/api/ipx800v4_refresh/A/on"), 200)
        self.assertIs(self.hass.data[DOMAIN]["b"], self.b)

    async def test_final_unload_then_setup(self):
        for entry_id in ("a", "b"):
            self.assertTrue(await async_unload_entry(self.hass, SimpleNamespace(entry_id=entry_id)))
        self.assertEqual(self.hass.data[DOMAIN], {})
        self.assertEqual(await self.get("/api/ipx800v4_refresh/on"), 401)
        self.add_entry("a", "A", "secret-a")
        self.assertEqual(await self.get("/api/ipx800v4_refresh/A/on"), 200)

    async def test_partial_setup_and_late_cleanup_are_safe(self):
        self.a.pop(PUSH_CONFIG)
        self.assertEqual(await self.get("/api/ipx800v4_refresh/A/on"), 401)
        _async_remove_entry_data(self.hass, "a", self.a)
        _async_remove_entry_data(self.hass, "a", self.a)
        replacement = self.add_entry("a", "A", "secret-a")
        _async_remove_entry_data(self.hass, "a", self.a)
        self.assertIs(self.hass.data[DOMAIN]["a"], replacement)
        self.assertTrue(await async_unload_entry(self.hass, SimpleNamespace(entry_id="never-initialized")))
        self.assertIs(self.hass.data[DOMAIN]["b"], self.b)


if __name__ == "__main__":
    unittest.main()
