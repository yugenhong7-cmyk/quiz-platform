"""
OpenAI 兼容大模型客户端（统一服务端管理）。

未配置 API Key 时返回"开发占位"内容并明确标记 is_placeholder=True，
绝不把占位内容伪装为真实 AI 生成。
"""
import json
import re
from typing import Any, Dict, List, Optional

import httpx

from ..config import settings


class AIClientError(Exception):
    pass


def get_ai_client(db=None) -> "AIClient":
    """构建 AI 客户端：优先读数据库 app_settings（系统设置界面保存的配置），
    未设置的项回退到环境变量。db 为 None 时仅用环境变量。"""
    if db is not None:
        from ..models import AppSetting

        def _g(key: str, default: str) -> str:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row and row.value else default

        return AIClient(
            api_base=_g("ai_api_base", settings.AI_API_BASE),
            api_key=_g("ai_api_key", settings.AI_API_KEY),
            model=_g("ai_model", settings.AI_MODEL),
            timeout=int(_g("ai_timeout", str(settings.AI_TIMEOUT))),
            max_tokens=int(_g("ai_max_tokens", str(settings.AI_MAX_TOKENS))),
        )
    return AIClient()


class AIClient:
    def __init__(self, api_base: str = "", api_key: str = "", model: str = "",
                 timeout: int = 0, max_tokens: int = 0):
        self.api_base = (api_base or settings.AI_API_BASE or "").rstrip("/")
        self.api_key = api_key or settings.AI_API_KEY
        self.model = model or settings.AI_MODEL
        self.timeout = timeout or settings.AI_TIMEOUT
        self.max_tokens = max_tokens or settings.AI_MAX_TOKENS

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7,
             json_mode: bool = False) -> Dict[str, Any]:
        """返回 {content, is_placeholder, model, error}。"""
        if not self.is_configured:
            return {
                "content": "",
                "is_placeholder": True,
                "model": self.model,
                "error": "AI 服务未配置（缺少 API Key）。这是开发占位状态，不代表真实模型回答。",
            }
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code >= 400:
                    raise AIClientError(f"API 返回 {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "is_placeholder": False, "model": self.model, "error": ""}
        except AIClientError as e:
            return {"content": "", "is_placeholder": True, "model": self.model, "error": str(e)}
        except Exception as e:
            return {"content": "", "is_placeholder": True, "model": self.model,
                    "error": f"AI 调用失败：{type(e).__name__}: {e}"}

    def test_connection(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "configured": False,
                    "message": "未配置 API Key。配置后可连接真实模型；当前 AI 功能为开发占位状态。"}
        result = self.chat([{"role": "user", "content": "请回复：连接测试成功"}], temperature=0)
        if result["is_placeholder"]:
            return {"ok": False, "configured": True, "message": result["error"], "model": self.model}
        return {"ok": True, "configured": True, "message": "连接成功",
                "model": self.model, "reply": result["content"][:100]}


# ---------- 高层业务封装 ----------

PLACEHOLDER_PREFIX = "【开发占位 · 非真实模型回答】"


def explain_question(client: AIClient, q: Dict[str, Any]) -> Dict[str, Any]:
    """AI 解析题目。"""
    opts = "\n".join(f"{o['label']}. {o['content']}" for o in q.get("options", []))
    prompt = (
        "你是一位耐心的考试辅导老师。请对下面这道题进行详细讲解。\n"
        "要求：1) 说明正确答案的理由；2) 逐一分析错误选项错在哪里；"
        "3) 归纳涉及的知识点；4) 指出容易混淆的概念。\n"
        "如果标准答案缺失或有争议，必须明确说明不确定性，不要编造权威答案。\n\n"
        f"题型：{q.get('qtype')}\n题干：{q.get('stem')}\n{opts}\n"
        f"标准答案：{q.get('answer')}\n已有解析：{q.get('explanation','') or '无'}"
    )
    r = client.chat([{"role": "user", "content": prompt}])
    if r["is_placeholder"]:
        return {
            "content": f"{PLACEHOLDER_PREFIX}\n\n未能调用真实模型（{r['error']}）。\n\n"
                       f"以下是基于题目规则的本地讲解摘要（非 AI 生成）：\n"
                       f"- 题型：{q.get('qtype')}；正确答案：{q.get('answer')}\n"
                       f"- 官方解析：{q.get('explanation') or '（未提供）'}\n"
                       f"请在「系统设置 → AI 配置」中填入 API Key 后获取完整 AI 讲解。",
            "is_placeholder": True,
        }
    return {"content": r["content"], "is_placeholder": False}


def hint_question(client: AIClient, q: Dict[str, Any]) -> Dict[str, Any]:
    """提示模式：只给思路，不泄露答案。"""
    opts = "\n".join(f"{o['label']}. {o['content']}" for o in q.get("options", []))
    prompt = (
        "你是学习教练。用户正在做题，**绝不能直接说出正确答案或答案字母**。\n"
        "请只给出启发式思路提示：解题切入点、相关概念提醒、排除法方向、需要回顾的知识。\n"
        "最后提醒用户可以自行作答后再看完整解析。\n\n"
        f"题干：{q.get('stem')}\n{opts}"
    )
    r = client.chat([{"role": "user", "content": prompt}], temperature=0.7)
    if r["is_placeholder"]:
        return {
            "content": f"{PLACEHOLDER_PREFIX}\n\nAI 提示不可用（{r['error']}）。\n\n"
                       f"本地提示（非 AI）：\n"
                       f"- 先仔细读题，圈出限定词（如“不正确”“最主要”）。\n"
                       f"- 回顾该知识点的定义与典型例子。\n"
                       f"- 使用排除法，先去掉明显错误的选项。",
            "is_placeholder": True,
        }
    return {"content": r["content"], "is_placeholder": False}


def chat_with_context(client: AIClient, history: List[Dict[str, str]],
                      context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """多轮答疑，可携带当前题目上下文。"""
    sys = (
        "你是 AI 学习助教，用简洁、通俗、鼓励式的中文回答。"
        "如果问题涉及具体题目，先基于题目信息分析；"
        "若信息不足或答案有争议，如实说明不确定性，不要编造。"
    )
    if context and context.get("stem"):
        opts = "\n".join(f"{o.get('label')}. {o.get('content')}" for o in context.get("options", []))
        sys += (
            f"\n\n当前题目上下文：\n题型：{context.get('qtype')}\n题干：{context.get('stem')}\n{opts}\n"
            f"标准答案：{context.get('answer')}\n解析：{context.get('explanation') or '无'}\n"
            f"用户作答：{context.get('user_answer', '（未作答）')}"
        )
    messages = [{"role": "system", "content": sys}] + history[-12:]
    r = client.chat(messages)
    if r["is_placeholder"]:
        return {
            "content": f"{PLACEHOLDER_PREFIX}\n\nAI 服务当前不可用：{r['error']}\n\n"
                       f"普通刷题、判题、错题本功能不受影响。配置 API Key 后即可启用智能答疑。",
            "is_placeholder": True,
        }
    return {"content": r["content"], "is_placeholder": False}


def generate_similar_questions(client: AIClient, q: Dict[str, Any],
                               count: int = 3, qtype: str = "single") -> Dict[str, Any]:
    """生成相似题（返回结构化 JSON，进草稿区）。"""
    opts = "\n".join(f"{o['label']}. {o['content']}" for o in q.get("options", []))
    prompt = (
        f"请基于下面这道题，生成 {count} 道**全新的**同类练习题（题型：{qtype}）。\n"
        "知识点保持一致，但题干、选项、答案必须全新，不得抄袭原题。\n"
        "只输出 JSON，格式：\n"
        '{"questions":[{"stem":"...","options":[{"label":"A","content":"..."},...],'
        '"answer":"B","explanation":"...","knowledge_points":["..."],"difficulty":2}]}\n'
        f"多选题 answer 用数组，判断题无 options 且 answer 为 true/false，填空题 answer 为数组。\n\n"
        f"原题：{q.get('stem')}\n{opts}\n答案：{q.get('answer')}\n知识点：{q.get('knowledge_points')}"
    )
    r = client.chat([{"role": "user", "content": prompt}], temperature=0.8, json_mode=False)
    if r["is_placeholder"]:
        return {"questions": [], "is_placeholder": True, "error": r["error"]}
    content = r["content"]
    # 尝试提取 JSON
    try:
        m = re.search(r"\{[\s\S]*\}", content)
        data = json.loads(m.group(0) if m else content)
        return {"questions": data.get("questions", []), "is_placeholder": False, "error": ""}
    except Exception as e:
        return {"questions": [], "is_placeholder": False, "error": f"模型输出 JSON 解析失败：{e}"}


def analyze_wrong_questions(client: AIClient, wrong_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """错题分析：薄弱知识点 + 复习建议。"""
    if not wrong_list:
        return {"content": "暂无错题记录。", "is_placeholder": False}
    summary = "\n".join(
        f"- [{w.get('qtype')}] {w.get('stem','')[:60]} | 错误 {w.get('wrong_count',1)} 次 | 知识点：{','.join(w.get('knowledge_points') or [])}"
        for w in wrong_list[:30]
    )
    prompt = (
        "你是学习规划师。请根据以下错题记录：\n"
        "1) 找出薄弱知识点（按优先级）；2) 分析错误原因模式；"
        "3) 给出个性化复习计划建议（分 7 天/14 天）。\n"
        "如果记录不足以下结论，请说明不确定性。\n\n" + summary
    )
    r = client.chat([{"role": "user", "content": prompt}])
    if r["is_placeholder"]:
        # 本地统计版
        kp_count: Dict[str, int] = {}
        for w in wrong_list:
            for k in (w.get("knowledge_points") or []):
                kp_count[k] = kp_count.get(k, 0) + 1
        top = sorted(kp_count.items(), key=lambda x: -x[1])[:5]
        lines = [f"{PLACEHOLDER_PREFIX}\n\n以下为本地统计（非 AI 生成）：", "薄弱知识点排序："]
        lines += [f"{i+1}. {k}（错 {v} 次）" for i, (k, v) in enumerate(top)] or ["（暂无知识点标签）"]
        lines.append("\n建议：优先重做错误次数最多的题目，并按间隔复习（1/2/4/7 天）重做。")
        return {"content": "\n".join(lines), "is_placeholder": True}
    return {"content": r["content"], "is_placeholder": False}


def ai_assist_parse(client: AIClient, raw_text: str) -> Dict[str, Any]:
    """AI 辅助整理混乱题目 → 统一 JSON。"""
    prompt = (
        "你是题库整理助手。请把下面混乱的题目文本整理成结构化 JSON。\n"
        "识别题型（single/multiple/truefalse/blank/shortanswer/calculation），"
        "提取题干、选项、答案、解析、知识点。输出 JSON：\n"
        '{"questions":[{"stem":"","options":[{"label":"A","content":""}],"answer":"B",'
        '"explanation":"","qtype":"single","knowledge_points":[],"difficulty":2}]}\n'
        "不确定的字段请在 uncertain_fields 数组中列出字段名。不要猜测不确定的正确答案。\n\n"
        f"{raw_text[:6000]}"
    )
    r = client.chat([{"role": "user", "content": prompt}], temperature=0.2)
    if r["is_placeholder"]:
        return {"questions": [], "is_placeholder": True, "error": r["error"]}
    try:
        m = re.search(r"\{[\s\S]*\}", r["content"])
        data = json.loads(m.group(0) if m else r["content"])
        return {"questions": data.get("questions", []), "is_placeholder": False, "error": ""}
    except Exception as e:
        return {"questions": [], "is_placeholder": False, "error": f"AI 输出解析失败：{e}"}


def grade_subjective(client: AIClient, q: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """主观题辅助评分。必须返回辅助评分标注。"""
    prompt = (
        "你是阅卷助手。请对主观题作答给出**参考评价**（辅助评分，不是绝对判定）。\n"
        "输出 JSON：{\"score\": 0-10, \"is_correct_suggestion\": true/false, \"comment\": \"...\", \"uncertainty\": \"...\"}\n"
        "评分要点缺失时必须在 uncertainty 中说明。\n\n"
        f"题干：{q.get('stem')}\n标准答案：{q.get('answer')}\n"
        f"评分要点：{q.get('explanation','') or '无'}\n用户作答：{user_answer}"
    )
    r = client.chat([{"role": "user", "content": prompt}], temperature=0.3)
    if r["is_placeholder"]:
        return {
            "is_correct": None,
            "ai_graded": False,
            "note": f"AI 辅助评分不可用（{r['error']}）。此题需人工评阅，系统不作自动判定。",
        }
    try:
        m = re.search(r"\{[\s\S]*\}", r["content"])
        data = json.loads(m.group(0) if m else r["content"])
        note = (
            f"【AI 辅助评分 · 非绝对判定】评分 {data.get('score','?')}/10。"
            f"{data.get('comment','')}"
            + (f" 不确定性：{data.get('uncertainty','')}" if data.get("uncertainty") else "")
        )
        return {
            "is_correct": bool(data.get("is_correct_suggestion")),
            "ai_graded": True,
            "note": note,
        }
    except Exception:
        return {
            "is_correct": None,
            "ai_graded": True,
            "note": f"【AI 辅助评分 · 非绝对判定】模型原始输出：{r['content'][:300]}",
        }
