/**
 * Members page - displays family member list with role management.
 *
 * Data flow:
 *   1. onLoad -> GET /v1/families/{id}/members -> member list
 *   2. onMemberTap -> show role picker (owner/admin can only be changed on family page)
 *   3. changeMemberRole -> POST /v1/families/{id}/members/{member_id}/role
 *
 * Note: owner and admin role changes must go through the family setup page.
 */
import { get, post } from '../../utils/api'

Page({
  data: {
    /** Whether data is being loaded */
    loading: true,
    /** List of family members */
    members: [],
    /** Whether to show the role picker action sheet */
    showRolePicker: false,
    /** Currently selected member id for role change */
    selectedMemberId: null,
    /** Available role options for the picker */
    roleOptions: [
      { label: '成员', value: 'member' },
      { label: '管理员', value: 'admin' },
      { label: '创建者', value: 'owner' },
    ],
  },

  onLoad() {
    this.loadMembers()
  },

  onShow() {
    // Re-fresh when returning from other pages
    if (!this.data.loading) {
      this.loadMembers()
    }
  },

  /**
   * Loads member list for the current family.
   * Falls back to GET /v1/families if currentFamilyId is not set.
   */
  loadMembers() {
    this.setData({ loading: true })

    const app = getApp()
    const familyId = app.globalData.currentFamilyId

    if (!familyId) {
      // Try fetching families first
      return get('/families')
        .then((res) => {
          const families = res.families || []
          if (families.length === 0) {
            this.setData({ members: [], loading: false })
            return
          }
          const first = families[0]
          app.globalData.currentFamilyId = first.family_id
          app.globalData.families = families
          return this.fetchMembers(first.family_id)
        })
        .catch(() => {
          wx.showToast({ title: '家庭成员加载失败', icon: 'none' })
          this.setData({ loading: false })
        })
    }

    return this.fetchMembers(familyId)
  },

  /**
   * Fetches members from the API.
   */
  fetchMembers(familyId) {
    return get(`/families/${familyId}/members`)
      .then((res) => {
        const members = res.members || []
        // Assign a color for avatar placeholder
        const colors = ['#07c160', '#1e88e5', '#e65100', '#7b1fa2', '#00897b', '#e53935']
        members.forEach((m, i) => {
          m.color = colors[i % colors.length]
        })
        this.setData({ members })
      })
      .catch(() => {
        wx.showToast({ title: '家庭成员加载失败', icon: 'none' })
        this.setData({ members: [] })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  },

  /**
   * Handles tapping on a member item.
   * Opens role picker for non-owner/non-admin members (as per spec: owner/admin
   * can only be modified through the family setup page).
   */
  onMemberTap(e) {
    const memberId = e.currentTarget.dataset.memberId
    const member = this.data.members.find((m) => m.member_id === memberId)
    if (!member) return

    // owner and admin roles can only be changed via family setup page
    if (member.role === 'owner' || member.role === 'admin') {
      wx.showToast({ title: `${this.roleLabel(member.role)}角色需通过家庭页面操作`, icon: 'none' })
      return
    }

    // Show role picker for regular members
    this.setData({
      showRolePicker: true,
      selectedMemberId: memberId,
    })
  },

  /**
   * Changes the role of the selected member.
   */
  changeMemberRole(e) {
    const newRole = e.currentTarget.dataset.role
    const { selectedMemberId } = this.data
    const app = getApp()
    const familyId = app.globalData.currentFamilyId

    if (!familyId || !selectedMemberId) return

    wx.showLoading({ title: '修改中...' })
    post(`/families/${familyId}/members/${selectedMemberId}/role`, { role: newRole })
      .then(() => {
        wx.showToast({ title: '角色已更新', icon: 'success' })
        this.setData({ showRolePicker: false, selectedMemberId: null })
        // Reload member list
        return this.fetchMembers(familyId)
      })
      .catch(() => {
        wx.showToast({ title: '角色修改失败', icon: 'none' })
      })
      .finally(() => {
        wx.hideLoading()
      })
  },

  /**
   * Closes the role picker action sheet.
   */
  closeRolePicker() {
    this.setData({ showRolePicker: false, selectedMemberId: null })
  },

  /**
   * Navigates back to the family page to manage invite codes.
   */
  goToFamily() {
    wx.navigateTo({ url: '/pages/family/index' })
  },

  /**
   * Maps server role value to a Chinese label.
   */
  roleLabel(role) {
    const map = {
      owner: '创建者',
      admin: '管理员',
      member: '成员',
    }
    return map[role] || role || '未知'
  },
})
