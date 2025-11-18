
# todo 没想清楚这个会话历史管理应该放哪里，AgentCore也合理，PE好像也行？


# @app.post("/session/append")
# async def append_message(req: AppendMessageReq):
#     if req.session_id not in _SESSION_HISTORY:
#         _SESSION_HISTORY[req.session_id] = []
#     _SESSION_HISTORY[req.session_id].append({"role": req.role, "content": req.content})
#     return {"ok": True, "len": len(_SESSION_HISTORY[req.session_id])}
#
#
# @app.get("/session/get/{session_id}")
# async def get_session(session_id: str):
#     return {"session_id": session_id, "history": _SESSION_HISTORY.get(session_id, [])}