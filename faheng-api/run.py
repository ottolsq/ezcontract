"""法衡 AI · 企业多智能体工作台 — API（Demo）"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
