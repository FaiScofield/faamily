/**
 * 家庭管家 - 小程序入口
 */
import { get, post, saveTokens, clearTokens } from './utils/api'

App({
  globalData: {
    userInfo: null,
    families: [],
    currentFamilyId: null,
  },

  onLaunch() {
    // 检查是否已有 token
    const token = wx.getStorageSync('access_token')
    if (token) {
      this.getUserInfo()
    }
  },

  /** 获取当前用户信息 */
  getUserInfo() {
    return get('/auth/me')
      .then((res) => {
        // Normalize: backend returns user_id, but pages expect id
        if (res.user_id && !res.id) {
          res.id = res.user_id
        }
        this.globalData.userInfo = res
        wx.setStorageSync('user_info', res)
        return res
      })
      .catch(() => {
        clearTokens()
        this.globalData.userInfo = null
      })
  },
})
