/**
 * Task create page - form to create a new task.
 *
 * Data flow:
 *   1. onLoad -> loadMembers() to populate assignee/reviewer pickers
 *   2. onSubmit -> POST /families/{familyId}/tasks with form data
 */
import { get, post } from '../../utils/api'

const PRIORITY_OPTIONS = [
  { label: '无', value: 0 },
  { label: '低', value: 1 },
  { label: '中', value: 2 },
  { label: '高', value: 3 },
]

Page({
  data: {
    /** Whether members are being loaded */
    loadingMembers: true,
    /** Whether the submit request is in-flight */
    submitting: false,
    /** Member options for picker */
    memberOptions: [],
    /** Form data */
    formData: {
      title: '',
      description: '',
      assigneeIndex: undefined,
      reviewerIndex: undefined,
      priorityIndex: 0,
      dueDate: '',
    },
    /** Priority picker options */
    priorityOptions: PRIORITY_OPTIONS,
  },

  onLoad() {
    this.loadMembers()
  },

  /**
   * Load family members to populate assignee/reviewer pickers.
   */
  loadMembers() {
    const familyId = this._getFamilyId()
    if (!familyId) {
      wx.showToast({ title: '请先选择家庭', icon: 'none' })
      this.setData({ loadingMembers: false })
      return
    }

    get(`/families/${familyId}/members`)
      .then((res) => {
        const options = (res.members || []).map((m) => ({
          label: m.display_name || m.user_id,
          value: m.user_id,
        }))
        this.setData({ memberOptions: options })
      })
      .catch(() => {
        wx.showToast({ title: '加载成员失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ loadingMembers: false })
      })
  },

  /**
   * Generic handler for input/textarea field changes.
   */
  onFieldChange(e) {
    const field = e.currentTarget.dataset.field
    const value = e.detail.value
    this.setData({
      [`formData.${field}`]: value,
    })
  },

  /** Handle assignee picker change */
  onAssigneeChange(e) {
    this.setData({
      'formData.assigneeIndex': parseInt(e.detail.value, 10),
    })
  },

  /** Handle reviewer picker change */
  onReviewerChange(e) {
    this.setData({
      'formData.reviewerIndex': parseInt(e.detail.value, 10),
    })
  },

  /** Handle priority picker change */
  onPriorityChange(e) {
    this.setData({
      'formData.priorityIndex': parseInt(e.detail.value, 10),
    })
  },

  /** Handle due date picker change */
  onDueDateChange(e) {
    this.setData({
      'formData.dueDate': e.detail.value,
    })
  },

  /**
   * Validate form fields and submit task.
   */
  onSubmit() {
    if (this.data.submitting) return

    const { formData } = this.data

    // Validate required fields
    if (!formData.title || !formData.title.trim()) {
      wx.showToast({ title: '请输入任务标题', icon: 'none' })
      return
    }

    const familyId = this._getFamilyId()
    if (!familyId) {
      wx.showToast({ title: '请先选择家庭', icon: 'none' })
      return
    }

    this.setData({ submitting: true })
    wx.showLoading({ title: '创建中...' })

    // Build request body
    const body = {
      title: formData.title.trim(),
    }

    if (formData.description) {
      body.description = formData.description
    }

    if (formData.assigneeIndex !== undefined) {
      body.assignee_user_id = this.data.memberOptions[formData.assigneeIndex].value
    }

    if (formData.reviewerIndex !== undefined) {
      body.reviewer_user_id = this.data.memberOptions[formData.reviewerIndex].value
    }

    body.priority = PRIORITY_OPTIONS[formData.priorityIndex].value

    if (formData.dueDate) {
      body.due_at = formData.dueDate
    }

    post(`/families/${familyId}/tasks`, body)
      .then(() => {
        wx.hideLoading()
        wx.showToast({ title: '创建成功', icon: 'success', duration: 1500 })
        setTimeout(() => {
          wx.navigateBack()
        }, 1500)
      })
      .catch((err) => {
        wx.hideLoading()
        wx.showToast({ title: err.message || '创建失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ submitting: false })
      })
  },

  /**
   * Get current family ID.
   */
  _getFamilyId() {
    const app = getApp()
    return app.globalData.currentFamilyId || wx.getStorageSync('currentFamilyId')
  },
})
