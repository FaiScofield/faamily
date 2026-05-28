/**
 * Task detail page - view task info, submissions, and perform actions.
 *
 * Data flow:
 *   1. onLoad(options) -> loadMembers() to resolve user names
 *   2. onLoad          -> fetchTask(options.task_id) + fetchSubmissions(task_id)
 *   3. Status transition  -> PUT /families/{familyId}/tasks/{taskId}/status
 *   4. Submit for review  -> POST /families/{familyId}/tasks/{taskId}/submit
 *   5. Review submission  -> PUT .../submissions/{subId}/review
 */
import { get, put, post } from '../../utils/api'

Page({
  data: {
    /** Current task object (null when not loaded / not found) */
    task: null,
    /** Submissions list */
    submissions: [],
    /** Member map: user_id -> display_name */
    memberMap: {},
    /** Loading state */
    loading: true,
    /** Current user's user_id (from storage) */
    currentUserId: '',
    /** Whether current user is the reviewer of this task */
    isReviewer: false,
    /** Whether current user is the assignee of this task */
    isAssignee: false,
    /** Available status transition buttons */
    statusActions: [],
    /** Whether to show the submit form */
    showSubmit: false,
    /** Submit note input value */
    submitNote: '',
  },

  onLoad(options) {
    const taskId = options.task_id
    if (!taskId) {
      wx.showToast({ title: '缺少任务ID', icon: 'none' })
      return
    }

    // Get current user ID from stored user info
    const userInfo = wx.getStorageSync('user_info') || {}
    this.setData({ currentUserId: userInfo.id || '' })

    this.loadMembers().then(() => {
      this.fetchTask(taskId)
      this.fetchSubmissions(taskId)
    })
  },

  /**
   * Load family members to resolve user_id -> display_name.
   */
  loadMembers() {
    const familyId = this._getFamilyId()
    if (!familyId) return Promise.resolve()

    return get(`/families/${familyId}/members`)
      .then((res) => {
        const map = {}
        ;(res.members || []).forEach((m) => {
          map[m.user_id] = m.display_name || m.user_id
        })
        this.setData({ memberMap: map })
      })
      .catch(() => {})
  },

  /**
   * Fetch task detail.
   */
  fetchTask(taskId) {
    const familyId = this._getFamilyId()
    if (!familyId) return

    get(`/families/${familyId}/tasks/${taskId}`)
      .then((task) => {
        this.setData({ task }, () => {
          this._computeActions()
        })
      })
      .catch(() => {
        wx.showToast({ title: '加载任务失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  },

  /**
   * Fetch submissions for this task.
   */
  fetchSubmissions(taskId) {
    const familyId = this._getFamilyId()
    if (!familyId) return

    get(`/families/${familyId}/tasks/${taskId}/submissions`)
      .then((res) => {
        this.setData({ submissions: res.submissions || [] })
      })
      .catch(() => {})
  },

  /**
   * Compute available status actions and submit visibility based on
   * task state and current user's role.
   */
  _computeActions() {
    const { task, currentUserId, memberMap } = this.data
    if (!task) return

    const isAssignee = task.assignee_user_id === currentUserId
    const isReviewer = task.reviewer_user_id === currentUserId

    this.setData({ isAssignee, isReviewer })

    const actions = []
    let showSubmit = false

    switch (task.status) {
      case 'pending':
        if (isAssignee) {
          actions.push({ label: '开始执行', status: 'in_progress', type: 'primary' })
        }
        break
      case 'in_progress':
        if (isAssignee) {
          showSubmit = true
        }
        break
      default:
        break
    }

    this.setData({ statusActions: actions, showSubmit })
  },

  /** Handle submit note textarea input */
  onSubmitNoteInput(e) {
    this.setData({ submitNote: e.detail.value })
  },

  /**
   * Transition task status.
   */
  onStatusTransition(e) {
    const status = e.currentTarget.dataset.status
    const familyId = this._getFamilyId()
    const taskId = this.data.task.task_id

    wx.showLoading({ title: '处理中...' })

    put(`/families/${familyId}/tasks/${taskId}/status`, { status })
      .then(() => {
        wx.hideLoading()
        wx.showToast({ title: '操作成功', icon: 'success' })
        this.fetchTask(taskId)
      })
      .catch((err) => {
        wx.hideLoading()
        wx.showToast({ title: err.message || '操作失败', icon: 'none' })
      })
  },

  /**
   * Submit the task for review.
   */
  onSubmitTask() {
    const familyId = this._getFamilyId()
    const taskId = this.data.task.task_id

    wx.showLoading({ title: '提交中...' })

    post(`/families/${familyId}/tasks/${taskId}/submit`, {
      note: this.data.submitNote || undefined,
    })
      .then(() => {
        wx.hideLoading()
        wx.showToast({ title: '提交成功', icon: 'success' })
        this.setData({ submitNote: '' })
        this.fetchTask(taskId)
        this.fetchSubmissions(taskId)
      })
      .catch((err) => {
        wx.hideLoading()
        wx.showToast({ title: err.message || '提交失败', icon: 'none' })
      })
  },

  /**
   * Review a submission (approve or reject).
   */
  onReview(e) {
    const subId = e.currentTarget.dataset.subId
    const action = e.currentTarget.dataset.action

    wx.showModal({
      title: action === 'approved' ? '确认通过' : '确认驳回',
      content: action === 'approved' ? '确定通过该提交？' : '确定驳回该提交？',
      success: (modalRes) => {
        if (!modalRes.confirm) return

        const familyId = this._getFamilyId()
        const taskId = this.data.task.task_id

        wx.showLoading({ title: '处理中...' })

        put(`/families/${familyId}/tasks/${taskId}/submissions/${subId}/review`, {
          status: action,
        })
          .then(() => {
            wx.hideLoading()
            wx.showToast({ title: action === 'approved' ? '已通过' : '已驳回', icon: 'success' })
            this.fetchTask(taskId)
            this.fetchSubmissions(taskId)
          })
          .catch((err) => {
            wx.hideLoading()
            wx.showToast({ title: err.message || '操作失败', icon: 'none' })
          })
      },
    })
  },

  /**
   * Resolve member user_id to display name.
   */
  memberName(userId) {
    return this.data.memberMap[userId] || userId || ''
  },

  /**
   * Convert status to Chinese label.
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
   * Convert priority number to Chinese label.
   */
  priorityLabel(priority) {
    const map = ['无', '低', '中', '高']
    return map[priority] || '无'
  },

  /**
   * Get current family ID.
   */
  _getFamilyId() {
    const app = getApp()
    return app.globalData.currentFamilyId || wx.getStorageSync('currentFamilyId')
  },
})
