<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Microphone, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()
const fileInput = ref(null)

// 录音能力探测：getUserMedia 仅在安全上下文（HTTPS / localhost）可用。
// 公网 IP 用 HTTP 直连时 navigator.mediaDevices 为 undefined → 走系统录音器上传兜底
const nativeSupported = ref(false)
// 兜底通道：<input type=file capture> 调起手机系统录音器，文件走 parse-voice-audio 转写
const useFallback = ref(false)

// 按钮状态机：idle → starting（等权限/建录音器）→ recording → processing（转写+解析）→ idle
// 防抖核心：非 idle 一律拒绝再入；processing 结束后短暂冷却
const phase = ref('idle')
let lockUntil = 0
const COOLDOWN_MS = 1000

// 录音：getUserMedia + MediaRecorder
let mediaStream = null
let mediaRecorder = null
let audioChunks = []
let stopTimer = null

const isRecording = computed(() => phase.value === 'recording')
const busy = computed(() => phase.value !== 'idle' || Date.now() < lockUntil)

/** 立即停止录音并释放麦克风（不等待 onstop 回调清理） */
function forceStopRecording() {
  clearTimeout(stopTimer)
  stopTimer = null
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    try {
      mediaRecorder.stop() // 触发 onstop → 进入转写流程
    } catch {
      // ignore
    }
  }
  mediaStream?.getTracks().forEach((t) => t.stop()) // 麦克风指示灯立即熄灭
}

onMounted(() => {
  nativeSupported.value =
    window.isSecureContext &&
    !!(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== 'undefined'
  if (!nativeSupported.value) useFallback.value = true
})

onBeforeUnmount(() => {
  cleanupRecording()
  lockUntil = 0
  phase.value = 'idle'
})

function cleanupRecording() {
  clearTimeout(stopTimer)
  stopTimer = null
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    try {
      mediaRecorder.stop()
    } catch {
      // ignore
    }
  }
  mediaRecorder = null
  mediaStream?.getTracks().forEach((t) => t.stop())
  mediaStream = null
  audioChunks = []
}

function pickMimeType() {
  // 常见浏览器录音格式优先级；后端统一转码
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
    'audio/mpeg',
  ]
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported?.(type)) return type
  }
  return ''
}

/** 转写 + 解析共用出口：成功后弹确认框 */
async function processBlob(blob, filename) {
  phase.value = 'processing'
  try {
    await store.parseVoiceAudio(blob, filename)
    store.voiceDialogVisible = true
  } catch {
    // error handled in store
  } finally {
    phase.value = 'idle'
    lockUntil = Date.now() + COOLDOWN_MS
  }
}

async function start() {
  // 防抖：启动中 / 录音中 / 识别上传中 / 冷却期内，一律忽略
  if (phase.value !== 'idle' || Date.now() < lockUntil) return

  if (!store.selectedArtistId) {
    ElMessage.warning('请先选择或新增一个人员')
    return
  }

  // 兜底通道：调起系统录音器（录完自动回来走 parse-voice-audio）
  if (useFallback.value) {
    fileInput.value?.click()
    return
  }

  phase.value = 'starting'
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    phase.value = 'idle'
    if (e?.name === 'NotAllowedError') {
      ElMessage.error('麦克风权限未开启，请在浏览器地址栏允许麦克风后重试')
    } else {
      ElMessage.error('无法访问麦克风：' + (e?.message || e))
    }
    return
  }

  mediaStream = stream
  audioChunks = []
  let mimeType = ''
  try {
    mimeType = pickMimeType()
    mediaRecorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream)
  } catch {
    // 极少数环境 MediaRecorder 构造失败：释放权限并提示
    cleanupRecording()
    phase.value = 'idle'
    ElMessage.error('当前浏览器录音初始化失败，请换用 Chrome/Edge 或系统录音上传')
    return
  }

  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) audioChunks.push(e.data)
  }

  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, {
      type: mediaRecorder?.mimeType || 'audio/webm',
    })
    cleanupRecording()

    if (!blob.size) {
      phase.value = 'idle'
      // 录音数据为空是本地问题（未授权/极短）；真正录到内容但 ASR
      // 识别为空的提示由后端 422 返回，避免这里弹两次
      ElMessage.warning('未能录到声音，请检查麦克风权限后重试')
      return
    }
    await processBlob(blob)
  }

  phase.value = 'recording'
  store.voiceText = ''
  store.voiceParsedEvents = []
  try {
    // timeslice 500ms：ondataavailable 持续产出分片，避免个别浏览器
    // 只在 stop 时一次性给数据导致的"停止无响应"问题
    mediaRecorder.start(500)
  } catch {
    mediaRecorder.start()
  }
  // 不设自动停止：语音内容长短不一，由用户点按结束；
  // 转写接口上限 20MB，opus 低码率录音远达不到，无需代管
}

/** 兜底通道：系统录音器返回的文件 → 直接转写（无录音过程，仅占用 processing 阶段） */
async function onFileChange(e) {
  const file = e.target.files?.[0]
  e.target.value = '' // 允许连续选择同一个文件
  if (!file) return

  if (!store.selectedArtistId) {
    ElMessage.warning('请先选择或新增一个人员')
    return
  }
  // 文件大小与后端 _MAX_AUDIO_BYTES 对齐
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.warning('录音文件过大（超过 20MB），请缩短录音时长')
    return
  }

  await processBlob(file, file.name)
}

/** 点击行为：录音中点击 = 立即结束并送去识别；其他状态走 start 防抖入口 */
function onClick() {
  if (phase.value === 'recording') {
    forceStopRecording()
    return
  }
  start()
}
</script>

<template>
  <div class="voice-fab" @click="onClick">
    <div :class="['pulse-ring', { recording: isRecording }]"></div>
    <div :class="['btn', { recording: isRecording }]">
      <el-icon v-if="phase === 'processing'"><Loading class="spin" /></el-icon>
      <el-icon v-else><Microphone /></el-icon>
    </div>
    <div v-if="phase === 'processing'" class="tip">识别中…</div>
    <div v-else-if="isRecording" class="tip">正在听（点击结束）</div>
    <div v-else class="tip">语音录入</div>
    <!-- HTTP 等非安全上下文：调起手机系统录音器，录完直接上传转写 -->
    <input
      v-show="false"
      ref="fileInput"
      type="file"
      accept="audio/*"
      capture
      @change="onFileChange"
    />
  </div>
</template>

<style scoped>
.voice-fab {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  /* 消掉移动端 300ms 延迟与双击缩放误触 */
  touch-action: manipulation;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.btn {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #2459a9;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  box-shadow: 0 6px 18px rgba(36, 89, 169, 0.35);
  transition: all 0.2s;
}

.btn.recording {
  background: #e74c3c;
  box-shadow: 0 6px 18px rgba(231, 76, 60, 0.35);
}

.spin {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  to {
    transform: rotate(360deg);
  }
}

.pulse-ring {
  position: absolute;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 2px solid #2459a9;
  opacity: 0;
}

.pulse-ring.recording {
  animation: pulse 1.4s infinite;
}

@keyframes pulse {
  0% {
    transform: scale(1);
    opacity: 0.5;
  }
  100% {
    transform: scale(1.6);
    opacity: 0;
  }
}

.tip {
  font-size: 12px;
  color: #2459a9;
  background: #fff;
  padding: 2px 8px;
  border-radius: 999px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

@media (max-width: 768px) {
  .voice-fab {
    right: 16px;
    bottom: 16px;
  }

  .btn {
    width: 64px;
    height: 64px;
    font-size: 28px;
  }

  .pulse-ring {
    width: 64px;
    height: 64px;
  }

  .tip {
    font-size: 13px;
  }
}
</style>
