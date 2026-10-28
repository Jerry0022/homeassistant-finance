"""Open-question endpoints (admin only; the list shows bookings)."""

from __future__ import annotations

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN
from ..manager._questions import QuestionError
from ._helpers import _get_manager


class _AdminView(HomeAssistantView):
    requires_auth = True

    @staticmethod
    def _is_admin(request: web.Request) -> bool:
        user = request.get("hass_user")
        return bool(user and user.is_admin)


class FinanceDashboardQuestionsView(_AdminView):
    """``GET /api/finance_dashboard/questions`` -- this week's open questions."""

    url = f"/api/{DOMAIN}/questions"
    name = f"api:{DOMAIN}:questions"

    async def get(self, request: web.Request) -> web.Response:
        if not self._is_admin(request):
            return self.json({"error": "admin_required"}, status_code=403)
        manager = _get_manager(request.app["hass"])
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)
        return self.json(manager.get_questions())


class FinanceDashboardQuestionAnswerView(_AdminView):
    """``POST /api/finance_dashboard/questions/answer``."""

    url = f"/api/{DOMAIN}/questions/answer"
    name = f"api:{DOMAIN}:questions:answer"

    async def post(self, request: web.Request) -> web.Response:
        if not self._is_admin(request):
            return self.json({"error": "admin_required"}, status_code=403)
        manager = _get_manager(request.app["hass"])
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)
        try:
            body = await request.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self.json({"error": "invalid_body"}, status_code=400)
        try:
            result = await manager.async_answer_question(
                question_id=body.get("id"),
                category=body.get("category"),
                reach=body.get("reach"),
                owner=body.get("owner") or None,
                user_id=request["hass_user"].id,
            )
        except QuestionError as err:
            return self.json({"error": err.code, "detail": err.detail}, status_code=400)
        return self.json(result)
