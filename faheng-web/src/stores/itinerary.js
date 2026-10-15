import { defineStore } from 'pinia'
import api from '../api'
import { ElMessage } from 'element-plus'

const COLORS = [
  '#2459a9',
  '#e74c3c',
  '#27ae60',
  '#f39c12',
  '#8e44ad',
  '#16a085',
  '#2c3e50',
  '#d35400',
]

export const useItineraryStore = defineStore('itinerary', {
  state: () => ({
    artists: [],
    selectedArtistId: '',
    currentMonth: '', // YYYY-MM
    monthEvents: [],
    selectedDate: '', // YYYY-MM-DD
    dailyEvents: [],
    loading: false,
    // 语音录入
    voiceRecording: false,
    voiceText: '',
    voiceParsedEvents: [],
    voiceDialogVisible: false,
    voiceSaving: false,
  }),

  getters: {
    selectedArtist(s) {
      return s.artists.find((a) => a.id === s.selectedArtistId) || null
    },
    monthDates(s) {
      // 构建当月日期格子
      const [year, month] = s.currentMonth.split('-').map(Number)
      const firstDay = new Date(year, month - 1, 1)
      const lastDay = new Date(year, month, 0)
      const startOffset = firstDay.getDay() // 0 = Sunday
      const days = []
      // 前缀空白
      for (let i = 0; i < startOffset; i++) {
        days.push({ day: '', date: '' })
      }
      for (let d = 1; d <= lastDay.getDate(); d++) {
        const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
        days.push({ day: d, date })
      }
      return days
    },
    eventsByDate(s) {
      const map = {}
      s.monthEvents.forEach((ev) => {
        if (!map[ev.event_date]) map[ev.event_date] = []
        map[ev.event_date].push(ev)
      })
      return map
    },
  },

  actions: {
    initMonth() {
      const now = new Date()
      this.currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
      this.selectedDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    },

    async fetchArtists() {
      try {
        const { data } = await api.get('/itinerary/artists')
        this.artists = data.artists || []
        if (this.artists.length && !this.selectedArtistId) {
          this.selectedArtistId = this.artists[0].id
        }
      } catch (e) {
        ElMessage.error('加载艺人列表失败')
      }
    },

    async createArtist(name) {
      const color = COLORS[this.artists.length % COLORS.length]
      try {
        const { data } = await api.post('/itinerary/artists', { name, color })
        this.artists.unshift(data)
        this.selectedArtistId = data.id
        ElMessage.success(`已添加艺人 ${data.name}`)
        return data
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '添加艺人失败')
        throw e
      }
    },

    async deleteArtist(artistId) {
      try {
        await api.delete(`/itinerary/artists/${artistId}`)
        this.artists = this.artists.filter((a) => a.id !== artistId)
        if (this.selectedArtistId === artistId) {
          this.selectedArtistId = this.artists[0]?.id || ''
        }
        ElMessage.success('已删除艺人')
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '删除艺人失败')
      }
    },

    selectArtist(artistId) {
      this.selectedArtistId = artistId
      this.fetchMonthEvents()
    },

    changeMonth(delta) {
      const [year, month] = this.currentMonth.split('-').map(Number)
      const next = new Date(year, month - 1 + delta, 1)
      this.currentMonth = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`
      this.fetchMonthEvents()
    },

    setMonth(year, month) {
      this.currentMonth = `${year}-${String(month).padStart(2, '0')}`
      this.fetchMonthEvents()
    },

    async fetchMonthEvents() {
      if (!this.selectedArtistId || !this.currentMonth) return
      this.loading = true
      try {
        const { data } = await api.get(`/itinerary/artists/${this.selectedArtistId}/events`, {
          params: { month: this.currentMonth },
        })
        this.monthEvents = data.events || []
      } catch (e) {
        ElMessage.error('加载行程失败')
      } finally {
        this.loading = false
      }
    },

    async fetchDailyEvents(date) {
      if (!this.selectedArtistId || !date) return
      this.selectedDate = date
      try {
        const { data } = await api.get(`/itinerary/artists/${this.selectedArtistId}/events`, {
          params: { date },
        })
        this.dailyEvents = data.events || []
      } catch (e) {
        ElMessage.error('加载当日行程失败')
      }
    },

    async createEvent(payload) {
      try {
        const { data } = await api.post('/itinerary/events', payload)
        ElMessage.success('行程已保存')
        return data
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '保存行程失败')
        throw e
      }
    },

    async updateEvent(eventId, payload) {
      try {
        const { data } = await api.put(`/itinerary/events/${eventId}`, payload)
        ElMessage.success('行程已更新')
        return data
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '更新行程失败')
        throw e
      }
    },

    async deleteEvent(eventId) {
      try {
        await api.delete(`/itinerary/events/${eventId}`)
        ElMessage.success('已删除行程')
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '删除行程失败')
        throw e
      }
    },

    async parseVoice(text) {
      this.voiceSaving = true
      try {
        const { data } = await api.post('/itinerary/parse-voice', {
          text,
          default_artist_id: this.selectedArtistId,
        })
        this.voiceParsedEvents = (data.events || []).map((ev) => ({
          ...ev,
          _key: Math.random().toString(36).slice(2),
        }))
        return data
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '语音解析失败')
        throw e
      } finally {
        this.voiceSaving = false
      }
    },

    async parseVoiceAudio(blob, filename) {
      this.voiceSaving = true
      this.voiceText = ''
      try {
        const form = new FormData()
        // 手机录音 App 产出的 mime 常缺失或不准（如 iPhone 的 audio/x-m4a），
        // 后端按文件名后缀识别格式，故把原始文件名一并带上
        const ext = (blob.type.split('/')[1] || 'webm').split(';')[0]
        form.append('file', blob, filename || `voice.${ext}`)
        form.append('default_artist_id', this.selectedArtistId)
        const { data } = await api.post('/itinerary/parse-voice-audio', form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        this.voiceText = data.text || ''
        this.voiceParsedEvents = (data.events || []).map((ev) => ({
          ...ev,
          _key: Math.random().toString(36).slice(2),
        }))
        return data
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '语音识别失败')
        throw e
      } finally {
        this.voiceSaving = false
      }
    },

    async confirmVoiceEvents(events) {
      this.voiceSaving = true
      try {
        const { data } = await api.post('/itinerary/confirm', { events })
        ElMessage.success(`已确认 ${data.events?.length || 0} 条行程`)
        return data
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '确认保存失败')
        throw e
      } finally {
        this.voiceSaving = false
      }
    },

    resetVoice() {
      this.voiceRecording = false
      this.voiceText = ''
      this.voiceParsedEvents = []
      this.voiceDialogVisible = false
    },

    reset() {
      this.$reset()
    },
  },
})
