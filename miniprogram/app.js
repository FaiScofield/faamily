/**
 * 家庭管家 - 小程序入口
 */
import { post, saveTokens, clearTokens } from './utils/api'

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
    return post('/auth/me')
      .then((res) => {
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
