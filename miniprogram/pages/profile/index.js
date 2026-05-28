/**
 * Profile page - displays user profile, VIP status, and account settings.
 *
 * Data flow:
 *   1. onShow -> GET /v1/auth/me          -> current user info
 *   2. onShow -> GET /v1/vip/status        -> VIP status (level, expiry)
 *   3. logout -> clear tokens, reLaunch to login page
 */
import { get, clearTokens } from '../../utils/api'

Page({
  data: {
    /** Whether data is being loaded */
    loading: true,
    /** Current user info (nickname, avatar_url, etc.) */
    userInfo: null,
    /** VIP status object */
    vipStatus: null,
  },

  onShow() {
    this.loadProfile()
  },

  /**
   * Loads user profile and VIP status in parallel.
   */
  loadProfile() {
    this.setData({ loading: true })

    const cached = wx.getStorageSync('user_info')

    return Promise.all([
      get('/auth/me'),
      get('/vip/status'),
    ])
      .then(([me, vip]) => {
        // Merge cached avatar/nickname if needed
        const user = me.user || me
        if (!user.avatar_url && cached?.avatar_url) {
          user.avatar_url = cached.avatar_url
        }
        if (!user.nickname && cached?.nickname) {
          user.nickname = cached.nickname
        }

        // Update app global state
        const app = getApp()
        app.globalData.userInfo = user
        wx.setStorageSync('user_info', user)

        this.setData({
          userInfo: user,
          vipStatus: vip.status || vip,
        })
      })
      .catch(() => {
        // Fall back to cached user info if API fails
        if (cached) {
          this.setData({ userInfo: cached })
        }
        wx.showToast({ title: '个人信息加载失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ loading: false })
      })
  },

  /**
   * Navigates to the family management page.
   */
  goToFamily() {
    wx.switchTab({ url: '/pages/family/index' })
  },

  /**
   * Logs out the current user: clears tokens and jumps to the login page.
   */
  logout() {
    wx.showModal({
      title: '提示',
      content: '确定退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          clearTokens()
          wx.reLaunch({ url: '/pages/login/index' })
        }
      },
    })
  },
})
