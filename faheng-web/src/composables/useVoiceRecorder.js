import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../stores/itinerary'

/**
 * 录音状态机 composable：悬浮语音按钮与当日弹框语音按钮共用。
 *
 * 职责：能力探测（HTTPS getUserMedia / HTTP 系统录音器兜底）、
 * idle → starting → recording → processing 状态机、冷却防抖、
 * 转写+解析（store.parseVoiceAudio）。业务语义（人员校验、
 * 默认日期、解析结果去向）由调用方通过 options 注入。
 *
 * @param {object} options
 * @param {(blob: Blob, filename?: string) => void} options.onResult
 *        录音/选文件完成、转写解析成功后回调（默认已弹确认框）
 */
export function useVoiceRecorder({ onResult } = {}) {
  const store = useItineraryStore()

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

  function cleanupRecording() {
    clearTimeout(stopTimer)
    stopTimer = null
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      // 丢弃式停止：先摘掉 onstop，避免 dispose（关弹框/卸载）路径把
      // 用户已放弃的录音继续上传转写，并异步回踩 phase 造成状态竞态。
      // 正常点按结束走 forceStopRecording → stop() → onstop，不受影响。
      mediaRecorder.onstop = null
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

  /** 转写 + 解析共用出口：成功后回调 onResult（由调用方决定下一步） */
  async function processBlob(blob, filename) {
    phase.value = 'processing'
    try {
      await store.parseVoiceAudio(blob, filename)
      onResult?.()
    } catch {
      // error handled in store
    } finally {
      phase.value = 'idle'
      lockUntil = Date.now() + COOLDOWN_MS
    }
  }

  /** 兜底通道：动态建 <input type=file capture>，选完文件直接上传转写 */
  function openFilePicker() {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'audio/*'
    input.capture = ''
    input.style.display = 'none'
    input.onchange = async (e) => {
      const file = e.target.files?.[0]
      document.body.removeChild(input)
      if (!file) return
      // 文件大小与后端 _MAX_AUDIO_BYTES 对齐
      if (file.size > 20 * 1024 * 1024) {
        ElMessage.warning('录音文件过大（超过 20MB），请缩短录音时长')
        return
      }
      await processBlob(file, file.name)
    }
    document.body.appendChild(input)
    input.click()
  }

  async function start() {
    // 防抖：启动中 / 录音中 / 识别上传中 / 冷却期内，一律忽略
    if (phase.value !== 'idle' || Date.now() < lockUntil) return

    // 兜底通道：调起系统录音器（录完自动回来走 parse-voice-audio）
    if (useFallback.value) {
      openFilePicker()
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

  /** 点击行为统一入口：录音中 = 立即结束并送去识别；其他状态走 start 防抖入口 */
  function toggle() {
    if (phase.value === 'recording') {
      forceStopRecording()
      return
    }
    start()
  }

  /** 彻底停止并复位（弹框关闭 / 组件卸载时调用）：释放麦克风、状态归零 */
  function dispose() {
    cleanupRecording()
    lockUntil = 0
    phase.value = 'idle'
  }

  return {
    phase,
    isRecording,
    busy,
    start,
    stop: forceStopRecording,
    toggle,
    dispose,
    openFilePicker,
  }
}
