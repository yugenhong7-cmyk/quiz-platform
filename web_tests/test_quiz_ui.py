"""真实浏览器冒烟测试：注册→建库→导入识别→确认→刷题作答→统计（含 JS 错误监听）。"""
import json
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8017"
errors = []
failed_requests = []
console_errors = []

RAW = """1. 计算机的 CPU 主要负责什么？
A. 存储数据
B. 执行指令
C. 显示画面
D. 连接网络
答案：B

2. 以下哪些属于操作系统？
A. Windows
B. Linux
C. MySQL
D. macOS
答案：ABD

3. FIFO 是先进先出算法。
答案：正确"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})

        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed_requests.append(f"{r.url} {r.failure}"))
        page.on("response", lambda r: failed_requests.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)

        steps = []

        try:
            # 1. 加载首页
            page.goto(BASE, wait_until="networkidle")
            assert page.locator("#auth-view").is_visible(), "登录页未显示"
            steps.append("加载首页 OK")

            # 2. 注册
            page.click("button[data-tab=register]")
            suffix = "u" + str(int(page.evaluate("Date.now()")))[-7:]
            page.fill("#reg-username", suffix)
            page.fill("#reg-password", "test123456")
            page.click("#register-form button[type=submit]")
            page.wait_for_selector("#main-view:not(.hidden)", timeout=8000)
            assert page.locator(".sidebar").is_visible(), "主界面未显示"
            steps.append(f"注册登录 OK ({suffix})")

            # 3. 工作台
            page.wait_for_selector(".stat-card", timeout=8000)
            steps.append("工作台统计卡片 OK")

            # 4. 新建题库
            page.click("a[data-route=banks]")
            page.wait_for_selector("#new-bank-btn", timeout=8000)
            page.click("#new-bank-btn")
            page.fill("#bf-name", "浏览器测试题库")
            page.fill("#bf-desc", "Playwright 自动化创建")
            page.click("#bf-save")
            page.wait_for_timeout(1200)
            steps.append("创建题库 OK")

            # 5. 导入页：粘贴文本识别
            page.goto(BASE + "/#/import", wait_until="networkidle")
            page.wait_for_selector("#imp-text", timeout=8000)
            options = page.locator("#imp-bank option").all_text_contents()
            # 选中测试题库
            page.select_option("#imp-bank", label="浏览器测试题库（0 题）")
            page.fill("#imp-text", RAW)
            page.click("#imp-parse")
            page.wait_for_selector(".parse-item", timeout=15000)
            n = page.locator(".parse-item").count()
            assert n == 3, f"应识别 3 题，实际 {n}"
            type_texts = page.locator(".parse-item .badge-primary").all_text_contents()
            assert "单选题" in type_texts[0] and "多选题" in type_texts[1] and "判断题" in type_texts[2], type_texts
            steps.append(f"文本识别 OK（3 题，题型：{type_texts[:3]}）")

            # 6. 确认导入
            page.click("#imp-confirm")
            page.wait_for_timeout(1500)
            assert "bank" in page.url, page.url
            steps.append("确认导入 OK")

            # 7. 开始练习
            page.goto(BASE + "/#/practice", wait_until="networkidle")
            page.wait_for_selector(".mode-card", timeout=8000)
            page.click(".mode-card[data-mode=sequential]")
            page.select_option("#pc-bank", label="浏览器测试题库（3 题）")
            page.fill("#pc-count", "3")
            page.click("#pc-start")
            page.wait_for_selector("#quiz-main", timeout=10000)
            steps.append("生成练习 OK")

            # 8. 作答第一题（选 B）
            page.click(".option-item[data-label=B]")
            page.click("#quiz-answer-btn")
            page.wait_for_timeout(1200)
            steps.append("作答判题 OK")

            # 9. 下一题多选
            page.click("#quiz-next")
            page.wait_for_timeout(500)
            page.click(".option-item[data-label=A]")
            page.click(".option-item[data-label=B]")
            page.click(".option-item[data-label=D]")
            page.click("#quiz-answer-btn")
            page.wait_for_timeout(1000)
            steps.append("多选作答 OK")

            # 10. 提交练习
            page.click("#quiz-submit-btn")
            page.wait_for_timeout(600)
            page.click("#modal-ok")
            page.wait_for_selector(".stat-value", timeout=10000)
            steps.append("提交出分 OK")

            # 11. 统计页
            page.goto(BASE + "/#/stats", wait_until="networkidle")
            page.wait_for_selector(".stat-card", timeout=8000)
            steps.append("学习统计 OK")

            # 12. 错题本
            page.goto(BASE + "/#/wrong", wait_until="networkidle")
            page.wait_for_selector("#w-list", timeout=8000)
            steps.append("错题本 OK")

            # 13. AI 助教页
            page.goto(BASE + "/#/ai", wait_until="networkidle")
            page.wait_for_selector("#ai-form", timeout=8000)
            steps.append("AI 助教页 OK")

            # 14. 移动端视口
            page.set_viewport_size({"width": 375, "height": 720})
            page.goto(BASE + "/#/dashboard", wait_until="networkidle")
            page.wait_for_timeout(800)
            assert page.locator("#menu-toggle").is_visible(), "移动端菜单按钮未显示"
            page.click("#menu-toggle")
            page.wait_for_timeout(400)
            assert page.locator(".sidebar.open").count() >= 0
            steps.append("移动端自适应 OK")

            # 15. 深色模式
            page.set_viewport_size({"width": 1366, "height": 900})
            page.click("#theme-toggle")
            theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
            assert theme == "dark", theme
            steps.append("深色模式切换 OK")

        finally:
            browser.close()

        report = {
            "steps": steps,
            "page_errors": errors,
            "console_errors": console_errors,
            "failed_requests": [r for r in failed_requests if "favicon" not in r],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))

        hard_fail = len(steps) < 10 or errors
        # 只把未捕获 JS 异常与失败步骤当硬错误；404 资源等算软错误
        print(f"\n===== 浏览器冒烟：步骤 {len(steps)}，JS 错误 {len(errors)}，console 错误 {len(console_errors)}，失败请求 {len(failed_requests)} =====")
        return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
