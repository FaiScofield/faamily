/**
 * Tasks page - displays task list with tab filters.
 *
 * Data flow:
 *   1. onLoad -> loadMembers() to get member name map
 *   2. onLoad -> fetchTasks() with current tab status filter
 *   3. onPullDownRefresh -> re-fetch tasks
 */
import { get } from '../../utils/api'

const TABS = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待办' },
  { key: 'in_progress', label: '进行中' },
  { key: 'done', label: '已完成' },
]

Page({
  data: {
    /** Available tab definitions */
    tabs: TABS,
    /** Currently active tab key */
    currentTab: 'all',
    /** Task list */
    tasks: [],
    /** Member map: user_id -> display_name */
    memberMap: {},
    /** Loading state */
    loading: true,
  },

  onLoad() {
    this.loadMembers().then(() => this.fetchTasks())
  },

  onPullDownRefresh() {
    this.fetchTasks().finally(() => wx.stopPullDownRefresh())
  },

  /**
   * Load family members to resolve user_id -> display_name.
   */
  loadMembers() {
    const familyId = this._getFamilyId()
    if (!familyId) {
      this.setData({ loading: false })
      return Promise.resolve()
    }

    return get(`/families/${familyId}/members`)
      .then((res) => {
        const map = {}
        ;(res.members || []).forEach((m) => {
          map[m.user_id] = m.display_name || m.user_id
        })
        this.setData({ memberMap: map })
      })
      .catch(() => {
        // Non-critical; continue without member names
      })
  },

  /**
   * Fetch tasks with current tab filter.
   */
  fetchTasks() {
    const familyId = this._getFamilyId()
    if (!familyId) {
      this.setData({ tasks: [], loading: false })
      return Promise.reject(new Error('No family selected'))
    }

    this.setData({ loading: true })

    const params = {}
    const tab = this.data.currentTab

    if (tab === 'done') {
      params.status = 'done'
    } else if (tab !== 'all') {
      params.status = tab
    }

    return get(`/families/${familyId}/tasks`, params)
      .then((res) => {
        let tasks = res.tasks || []

        // For the "done" tab, also include "rejected" tasks
        if (tab === 'done') {
          params.status = 'rejected'
          return get(`/families/${familyId}/tasks`, params).then((res2) => {
            const rejectedTasks = res2.tasks || []
            tasks = tasks.concat(rejectedTasks)
            this.setData({ tasks })
          })
        }

        this.setData({ tasks })
      })
      .catch(() => {
        wx.showToast({ title: '加载失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  },

  /** Tab switch handler */
  onTabChange(e) {
    const key = e.currentTarget.dataset.key
    if (key === this.data.currentTab) return
    this.setData({ currentTab: key }, () => {
      this.fetchTasks()
    })
  },

  /** Navigate to task detail page */
  goToDetail(e) {
    const taskId = e.currentTarget.dataset.taskId
    wx.navigateTo({ url: `/pages/task-detail/index?task_id=${taskId}` })
  },

  /**
   * Resolve member user_id to display name.
   */
  memberName(userId) {
    return this.data.memberMap[userId] || userId || ''
  },

  /**
   * Convert status key to Chinese label.
   */
  statusLabel(status) {
    const map = {
      pending: '待办',
      in_progress: '进行中',
      submitted: '已提交',
      done: '已完成',
      rejected: '已驳回',
    }
    return map[status] || status
  },

  /**
   * Get current family ID from app global data or storage.
   */
  _getFamilyId() {
    const app = getApp()
    return app.globalData.currentFamilyId || wx.getStorageSync('currentFamilyId')
  },
})
