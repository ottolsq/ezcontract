<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Refresh } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const form = reactive({
  username: '',
  password: '',
  captcha: '',
})
const captchaCode = ref('')
const submitting = ref(false)

/** 生成 4 位验证码（数字+大小写字母，排除易混字符） */
function makeCaptcha() {
  const chars = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
  let s = ''
  for (let i = 0; i < 4; i++) {
    s += chars[Math.floor(Math.random() * chars.length)]
  }
  return s
}

/** 在 canvas 上绘制带干扰的验证码 */
function drawCaptcha() {
  const canvas = captchaCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const w = canvas.width
  const h = canvas.height
  ctx.clearRect(0, 0, w, h)
  // 背景
  ctx.fillStyle = '#f0f4fa'
  ctx.fillRect(0, 0, w, h)
  // 干扰线
  for (let i = 0; i < 4; i++) {
    ctx.strokeStyle = `rgba(36,89,169,${0.15 + Math.random() * 0.2})`
    ctx.beginPath()
    ctx.moveTo(Math.random() * w, Math.random() * h)
    ctx.lineTo(Math.random() * w, Math.random() * h)
    ctx.lineWidth = 1
    ctx.stroke()
  }
  // 字符
  ctx.font = 'bold 22px "Microsoft YaHei", Inter, sans-serif'
  ctx.textBaseline = 'middle'
  const code = captchaCode.value
  const cw = w / code.length
  for (let i = 0; i < code.length; i++) {
    const ch = code[i]
    ctx.save()
    const x = cw * i + cw / 2
    const y = h / 2
    const angle = (Math.random() - 0.5) * 0.6
    ctx.translate(x, y)
    ctx.rotate(angle)
    ctx.fillStyle = `hsl(${210 + Math.random() * 30}, 70%, ${30 + Math.random() * 20}%)`
    ctx.fillText(ch, -8, 0)
    ctx.restore()
  }
  // 干扰点
  for (let i = 0; i < 20; i++) {
    ctx.fillStyle = `rgba(36,89,169,${0.2 + Math.random() * 0.3})`
    ctx.beginPath()
    ctx.arc(Math.random() * w, Math.random() * h, 1, 0, Math.PI * 2)
    ctx.fill()
  }
}

function refreshCaptcha() {
  captchaCode.value = makeCaptcha()
  drawCaptcha()
}

const captchaCanvas = ref(null)

async function onSubmit() {
  if (!form.username.trim() || !form.password.trim()) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  if (!form.captcha.trim()) {
    ElMessage.warning('请输入验证码')
    return
  }
  if (form.captcha.trim().toUpperCase() !== captchaCode.value) {
    ElMessage.error('验证码错误')
    refreshCaptcha()
    form.captcha = ''
    return
  }
  submitting.value = true
  try {
    await auth.login({
      username: form.username.trim(),
      password: form.password,
    })
    ElMessage.success('登录成功')
    router.push('/')
  } catch {
    refreshCaptcha()
    form.captcha = ''
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  refreshCaptcha()
})
</script>

<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <section class="brand-side">
      <div class="brand-header">
        <span class="brand-logo">⚖️</span>
        <span class="brand-name">法衡 <span class="brand-name-accent">AI</span></span>
      </div>

      <div class="brand-hero">
        <h1>
          企业多智能体工作台
          <span class="brand-sub">Enterprise Multi-Agent Workspace</span>
        </h1>
        <p class="brand-lead">
          法衡 AI 持续扩展合同起草、风险审查、履约提醒、会议纪要等企业智能体——<br />
          AI 负责识别与生成，人负责确认与决策，让每一次内容发布都在风险可控之内。
        </p>
      </div>

      <ul class="feature-list">
        <li><span class="dot"></span>全维度数据采集</li>
        <li><span class="dot"></span>急速准确预审</li>
        <li><span class="dot"></span>发布前合规审核</li>
      </ul>

      <footer class="brand-footer">
        © 法衡 AI · 仅供演示 AI 辅助 · 内容均由模型生成
      </footer>
    </section>

    <!-- 右侧登录区 -->
    <section class="login-side">
      <div class="login-card">
        <header class="login-header">
          <h2>欢迎回来</h2>
          <p>请使用管理员分配的账号登录</p>
        </header>

        <el-form class="login-form" @submit.prevent="onSubmit">
          <el-form-item>
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              size="large"
              :prefix-icon="User"
              autocomplete="username"
            />
          </el-form-item>

          <el-form-item>
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              autocomplete="current-password"
            />
          </el-form-item>

          <el-form-item>
            <div class="captcha-row">
              <el-input
                v-model="form.captcha"
                placeholder="请输入验证码"
                size="large"
                maxlength="4"
                @keyup.enter="onSubmit"
              />
              <div
                class="captcha-canvas-wrap"
                @click="refreshCaptcha"
                title="点击刷新"
              >
                <canvas
                  ref="captchaCanvas"
                  width="120"
                  height="40"
                  class="captcha-canvas"
                />
                <el-icon class="captcha-refresh"><Refresh /></el-icon>
              </div>
            </div>
          </el-form-item>

          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="submitting"
            @click="onSubmit"
          >
            登 录
          </el-button>
        </el-form>
      </div>

      <div class="login-meta">
        <span class="meta-tag">DEMO</span>
        <span>法衡 AI · 企业多智能体工作台</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  background: #f5f7fb;
}

/* —— 左侧 —— */
.brand-side {
  position: relative;
  padding: 56px 64px;
  display: flex;
  flex-direction: column;
  color: #1d2b4f;
  background:
    radial-gradient(circle at 20% 10%, rgba(36, 89, 169, 0.08), transparent 40%),
    radial-gradient(circle at 80% 90%, rgba(36, 89, 169, 0.06), transparent 50%),
    #f5f7fb;
  overflow: hidden;
}

.brand-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 56px;
}

.brand-logo {
  font-size: 26px;
}

.brand-name {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.brand-name-accent {
  color: #2459a9;
}

.brand-hero {
  max-width: 520px;
  margin-bottom: 40px;
}

.brand-hero h1 {
  margin: 0 0 18px;
  font-size: 38px;
  font-weight: 700;
  line-height: 1.25;
}

.brand-sub {
  display: block;
  margin-top: 8px;
  font-size: 14px;
  font-weight: 400;
  color: #9aabbe;
  letter-spacing: 1px;
}

.brand-lead {
  margin: 0;
  font-size: 15px;
  line-height: 1.8;
  color: #66758a;
}

.feature-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 14px;
  max-width: 420px;
}

.feature-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  font-size: 14px;
  color: #1d2b4f;
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(36, 89, 169, 0.04);
}

.feature-list .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2459a9, #5a8de0);
}

.brand-footer {
  margin-top: auto;
  font-size: 12px;
  color: #9aabbe;
  padding-top: 32px;
}

/* —— 右侧 —— */
.login-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 56px 32px;
  background: #f5f7fb;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 14px;
  padding: 36px 32px 32px;
  box-shadow: 0 10px 40px rgba(36, 89, 169, 0.08);
}

.login-header {
  margin-bottom: 28px;
}

.login-header h2 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
}

.login-header p {
  margin: 0;
  font-size: 13px;
  color: #9aabbe;
}

.login-form {
  display: flex;
  flex-direction: column;
}

.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
}

.captcha-row :deep(.el-input) {
  flex: 1;
}

.captcha-canvas-wrap {
  position: relative;
  width: 120px;
  height: 40px;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid #dcdfe6;
  background: #f0f4fa;
  flex-shrink: 0;
}

.captcha-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.captcha-refresh {
  position: absolute;
  right: 4px;
  top: 4px;
  font-size: 12px;
  color: #9aabbe;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 4px;
  padding: 1px 2px;
}

.login-btn {
  width: 100%;
  margin-top: 8px;
  font-size: 15px;
  letter-spacing: 4px;
}

.login-meta {
  margin-top: 28px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #9aabbe;
}

.meta-tag {
  background: #eaf2ff;
  color: #2459a9;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}

/* —— 响应式 —— */
@media (max-width: 900px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .brand-side {
    padding: 32px 24px;
  }
  .brand-hero h1 {
    font-size: 26px;
  }
  .feature-list {
    display: none;
  }
  .login-side {
    padding: 32px 16px;
  }
}
</style>
