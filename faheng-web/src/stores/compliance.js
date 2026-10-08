import { defineStore } from 'pinia'
import api from '../api'
import { ElMessage } from 'element-plus'
import { useNotificationsStore } from './notifications'

export const useComplianceStore = defineStore('compliance', {
  state: () => ({
    // 视图状态机：empty（无合同）→ processing（提取中）→ list（合同列表）→ detail（节点表）
    phase: 'empty',
    contracts: [],
    currentId: '',
    contract: null, // detail payload: { contract, milestones }
    uploading: false,
    status: '',
    error: '',
    progressStage: '',
    pollingTimer: null,
    milestoneFilter: 'pending', // 全部|pending|overdue|done|review
  }),

  getters: {
    milestones: (s) => s.contract?.milestones || [],
    /** 当前过滤后的节点列表 */
    visibleMilestones(s) {
      const list = this.milestones
      switch (s.milestoneFilter) {
        case 'pending':
          return list.filter((m) => m.status === 'pending')
        case 'overdue':
          return list.filter(
            (m) => m.status === 'pending' && m.days_left != null && m.days_left < 0,
          )
        case 'done':
          return list.filter((m) => m.status !== 'pending')
        case 'review':
          return list.filter((m) => m.needs_review === 1)
        default:
          return list
      }
    },
    /** 顶部统计条 */
    stats() {
      const list = this.milestones
      return {
        total: list.length,
        pending: list.filter((m) => m.status === 'pending').length,
        dueSoon7: list.filter(
          (m) =>
            m.status === 'pending' &&
            m.days_left != null &&
            m.days_left >= 0 &&
            m.days_left <= 7,
        ).length,
        overdue: list.filter(
          (m) => m.status === 'pending' && m.days_left != null && m.days_left < 0,
        ).length,
        done: list.filter((m) => m.status === 'done').length,
      }
    },
  },

  actions: {
    async fetchContracts() {
      const { data } = await api.get('/compliance/contracts')
      this.contracts = data.contracts || []
      this.phase = this.contracts.length ? 'list' : 'empty'
    },

    async uploadFile(file) {
      this.uploading = true
      try {
        const fd = new FormData()
        fd.append('file', file)
        const { data } = await api.post('/compliance/upload', fd)
        await this.startExtract(data.contract_id)
        return data
      } finally {
        this.uploading = false
      }
    },

    async loadSample() {
      this.uploading = true
      try {
        const { data } = await api.post('/compliance/sample')
        await this.startExtract(data.contract_id)
        return data
      } finally {
        this.uploading = false
      }
    },

    async startExtract(contractId) {
      this.currentId = contractId
      await api.post(`/compliance/${contractId}/extract`)
      // 异步操作后检查：如果合同已被删除，不再继续
      if (this.currentId !== contractId) return
      this.phase = 'processing'
      this.status = 'processing'
      this.progressStage = '正在提取履约节点'
      this.error = ''
      this.poll()
    },

    async startExtractBackground(contractId) {
      // 后台启动提取，不改变当前视图状态
      await api.post(`/compliance/${contractId}/extract`)
    },

    poll() {
      clearTimeout(this.pollingTimer)
      if (!this.currentId) return
      this.pollingTimer = setTimeout(async () => {
        // 再次检查 currentId，防止在等待期间被删除
        if (!this.currentId) return
        try {
          const { data } = await api.get(`/compliance/${this.currentId}/status`)
          this.status = data.status
          this.progressStage = data.stage
          this.error = data.error || ''
          if (data.status === 'processing') {
            this.poll()
          } else if (data.status === 'completed') {
            await this.fetchContracts()
            await this.fetchDetail(this.currentId)
            ElMessage.success('履约节点提取完成')
          } else if (data.status === 'failed') {
            // 停在 processing 面板显示错误与重试
          }
        } catch (error) {
          // 如果是 404 错误（合同已被删除），停止轮询
          if (error.response?.status === 404 || !this.currentId) {
            return
          }
          // 其他网络错误继续轮询
          this.poll()
        }
      }, 1500)
    },

    async fetchDetail(contractId) {
      const { data } = await api.get(`/compliance/${contractId}`)
      this.contract = data
      this.currentId = contractId
      this.phase = 'detail'
      this.milestoneFilter = 'pending'
    },

    async retryExtract() {
      if (!this.currentId) return
      await api.post(`/compliance/${this.currentId}/extract`)
      this.phase = 'processing'
      this.status = 'processing'
      this.progressStage = '正在提取履约节点'
      this.error = ''
      this.poll()
    },

    async setMilestoneStatus(milestoneId, status) {
      const { data } = await api.post(`/compliance/milestones/${milestoneId}/status`, {
        status,
      })
      await this.fetchDetail(this.currentId)
      return data
    },

    async setDueDate(milestoneId, dueDate) {
      await api.put(`/compliance/milestones/${milestoneId}/due-date`, {
        due_date: dueDate || '',
      })
      await this.fetchDetail(this.currentId)
    },

    async deleteContract(contractId) {
      // 如果删除的是当前正在提取的合同，先停止轮询并跳转
      if (this.currentId === contractId) {
        clearTimeout(this.pollingTimer)
        this.currentId = ''
        this.contract = null
        this.phase = 'list'
      }
      await api.delete(`/compliance/${contractId}`)
      await this.fetchContracts()
      // 刷新通知列表，移除已删除合同的相关提醒
      const notificationsStore = useNotificationsStore()
      await notificationsStore.fetch()
      ElMessage.success('已删除合同及其履约数据')
    },

    goList() {
      clearTimeout(this.pollingTimer)
      this.contract = null
      this.phase = 'list'
      this.fetchContracts()
    },

    reset() {
      clearTimeout(this.pollingTimer)
      this.$reset()
    },
  },
})
