/**
 * Home page - shows current family, quick entries, and pending tasks.
 *
 * Data flow:
 *   1. onLoad  -> GET /v1/families          -> pick the first family
 *   2. onLoad  -> GET /v1/families/{id}/tasks?status=pending  -> pending task list
 *   3. onPullDownRefresh -> re-fetch both endpoints
 */
import { get } from '../../utils/api'

Page({
  data: {
    /** Current family info (null if user has no family) */
    currentFamily: null,
    /** List of pending tasks for the current family */
    pendingTasks: [],
    /** Whether data is being loaded for the first time */
    loading: true,
    /** Whether pull-to-refresh is active */
    refreshing: false,
  },

  onLoad() {
    this.loadData()
  },

  onShow() {
    // Re-fetch when returning from other pages (e.g. task created)
    if (!this.data.loading) {
      this.loadData()
    }
  },

  /** Hook called when user pulls down to refresh */
  onPullDownRefresh() {
    this.setData({ refreshing: true })
    this.loadData().finally(() => {
      wx.stopPullDownRefresh()
      this.setData({ refreshing: false })
    })
  },

  /**
   * Loads families then, if one exists, loads pending tasks for it.
   */
  loadData() {
    this.setData({ loading: true })

    return get('/families')
      .then((res) => {
        const families = res.families || []
        if (families.length === 0) {
          this.setData({ currentFamily: null, pendingTasks: [], loading: false })
          return
        }

        const family = families[0]
        this.setData({ currentFamily: family })

        // Update app global state
        const app = getApp()
        app.globalData.families = families
        app.globalData.currentFamilyId = family.family_id

        // Load pending tasks for this family
        return this.loadPendingTasks(family.family_id)
      })
      .catch(() => {
        wx.showToast({ title: '数据加载失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  },

  /**
   * Fetches pending tasks for the given family.
   */
  loadPendingTasks(familyId) {
    return get(`/families/${familyId}/tasks`, { status: 'pending' })
      .then((res) => {
        this.setData({ pendingTasks: res.tasks || [] })
      })
      .catch(() => {
        this.setData({ pendingTasks: [] })
      })
  },

  /**
   * Navigate to the family management page.
   */
  goToFamily() {
    wx.navigateTo({ url: '/pages/family/index' })
  },

  /**
   * Navigate to the task list page.
   */
  goToTasks() {
    wx.navigateTo({ url: '/pages/tasks/index' })
  },

  /**
   * Navigate to the documents page (placeholder).
   */
  goToDocuments() {
    wx.showToast({ title: '文档功能即将上线', icon: 'none' })
  },

  /**
   * Navigate to the task detail page.
   */
  goToTaskDetail(e) {
    const taskId = e.currentTarget.dataset.taskId
    wx.navigateTo({ url: `/pages/task-detail/index?task_id=${taskId}` })
  },
})
