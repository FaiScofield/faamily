/**
 * Family page - displays current family info, scenario templates, and invite management.
 *
 * Data flow:
 *   1. onLoad -> GET /v1/families -> pick first family OR use globalData.currentFamilyId
 *   2. onLoad -> GET /v1/families/{id} -> family detail
 *   3. onLoad -> GET /v1/families/{id}/invites -> existing invite code
 *   4. generateInviteCode -> POST /v1/families/{id}/invites -> new invite code
 *   5. initTemplates -> POST /v1/scenarios/templates/seed -> init scenario templates
 */
import { get, post } from '../../utils/api'

Page({
  data: {
    /** Whether data is being loaded */
    loading: true,
    /** Current family detail object */
    family: null,
    /** Current user's role label in this family */
    roleLabel: '',
    /** Number of family members */
    memberCount: 0,
    /** Number of active (enabled) scenario templates */
    activeTemplateCount: 0,
    /** Current invite code string */
    inviteCode: '',
    /** List of scenario templates */
    templates: [],
    /** Whether the init templates button is loading */
    initLoading: false,
  },

  onLoad() {
    this.loadFamilyData()
  },

  onShow() {
    // Re-fresh when returning from other pages
    if (!this.data.loading) {
      this.loadFamilyData()
    }
  },

  /**
   * Loads family info from the server.
   * Falls back to GET /v1/families if currentFamilyId is not set.
   */
  loadFamilyData() {
    this.setData({ loading: true })

    const app = getApp()
    let familyId = app.globalData.currentFamilyId

    const loadDetail = (fid) => {
      // Fetch family detail, invites, and templates in parallel
      return Promise.all([
        get(`/families/${fid}`),
        get(`/families/${fid}/invites`),
        this.loadTemplates(fid),
      ])
        .then(([familyData, inviteData]) => {
          const family = familyData.family || familyData
          this.setData({
            family,
            roleLabel: this.getRoleLabel(family.my_role),
            memberCount: family.member_count || 0,
            activeTemplateCount: family.active_template_count || 0,
            inviteCode: inviteData.code || inviteData.invite_code || '',
          })
        })
        .catch(() => {
          wx.showToast({ title: '家庭信息加载失败', icon: 'none' })
        })
        .finally(() => {
          this.setData({ loading: false })
        })
    }

    if (familyId) {
      return loadDetail(familyId)
    }

    // No cached familyId, fetch family list first
    return get('/families')
      .then((res) => {
        const families = res.families || []
        if (families.length === 0) {
          this.setData({ loading: false, family: null })
          return
        }
        const first = families[0]
        app.globalData.families = families
        app.globalData.currentFamilyId = first.family_id
        return loadDetail(first.family_id)
      })
      .catch(() => {
        wx.showToast({ title: '家庭信息加载失败', icon: 'none' })
        this.setData({ loading: false })
      })
  },

  /**
   * Loads scenario templates for the current family.
   */
  loadTemplates(familyId) {
    return get(`/families/${familyId}/templates`)
      .then((res) => {
        const templates = res.templates || []
        const activeCount = templates.filter((t) => t.is_enabled).length
        this.setData({ templates, activeTemplateCount: activeCount })
      })
      .catch(() => {
        this.setData({ templates: [], activeTemplateCount: 0 })
      })
  },

  /**
   * Generates a new invite code for the current family.
   */
  generateInviteCode() {
    const { family } = this.data
    if (!family || !family.family_id) {
      wx.showToast({ title: '请先选择家庭', icon: 'none' })
      return
    }

    wx.showLoading({ title: '生成中...' })
    post(`/families/${family.family_id}/invites`)
      .then((res) => {
        const code = res.code || res.invite_code || ''
        this.setData({ inviteCode: code })
        wx.showToast({ title: '邀请码已生成', icon: 'success' })
      })
      .catch(() => {
        wx.showToast({ title: '生成失败，请重试', icon: 'none' })
      })
      .finally(() => {
        wx.hideLoading()
      })
  },

  /**
   * Copies the invite code to clipboard.
   */
  copyInviteCode() {
    const { inviteCode } = this.data
    if (!inviteCode) {
      wx.showToast({ title: '暂无邀请码', icon: 'none' })
      return
    }
    wx.setClipboardData({
      data: inviteCode,
      success: () => {
        wx.showToast({ title: '已复制', icon: 'success' })
      },
    })
  },

  /**
   * Initialises default scenario templates via seed endpoint.
   */
  initTemplates() {
    this.setData({ initLoading: true })
    post('/scenarios/templates/seed')
      .then(() => {
        wx.showToast({ title: '初始化成功', icon: 'success' })
        // Reload templates
        const app = getApp()
        const familyId = app.globalData.currentFamilyId
        if (familyId) {
          return this.loadTemplates(familyId)
        }
      })
      .catch(() => {
        wx.showToast({ title: '初始化失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ initLoading: false })
      })
  },

  /**
   * Navigates to the members management page.
   */
  goToMembers() {
    wx.navigateTo({ url: '/pages/members/index' })
  },

  /**
   * Maps server role value to a Chinese label.
   */
  getRoleLabel(role) {
    const map = {
      owner: '创建者',
      admin: '管理员',
      member: '成员',
    }
    return map[role] || role || '未知'
  },
})
