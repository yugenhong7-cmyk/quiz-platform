# 真实浏览器冒烟测试（wcb-webapp-testing 脚手架）

## 运行前安装
    pip install -r requirements.txt
    playwright install chromium

## 运行
    python test_smoke.py

脚本会监听 pageerror / console / requestfailed，检查 4xx·5xx，做基础断言，
并把结果写入 report.json。任一错误非零即以非零退出码结束（便于 CI 阻断）。
