/**
 * Login page - handles WeChat Mini Program authentication flow.
 *
 * Flow:
 *   1. User clicks "微信一键登录" button (getUserProfile)
 *   2. wx.login() retrieves temporary code
 *   3. Backend exchanges code for openid/unionid and returns JWT tokens
 *   4. Token is persisted; user is redirected to the home page
 */
import { postNoAuth, saveTokens } from '../../utils/api'

Page({
  data: {
    /** Whether a login request is in-flight (used for button state) */
    isLogging: false,
  },

  /**
   * Triggered after the user grants WeChat user profile permission.
   * Combines wx.login + getUserProfile + backend auth in one atomic flow.
   */
  onGetUserProfile(e) {
    if (this.data.isLogging) return

    const { userInfo } = e.detail
    if (!userInfo) {
      wx.showToast({ title: '需要授权才能登录', icon: 'none' })
      return
    }

    this.setData({ isLogging: true })

    // Step 1: get temporary code from wx.login
    wx.login({
      success: (loginRes) => {
        if (!loginRes.code) {
          this._onError('微信登录失败，请重试')
          return
        }

        // Step 2: call backend WeChat login API
        this._wechatLogin(loginRes.code, userInfo)
      },
      fail: () => {
        this._onError('获取授权失败，请检查网络')
      },
    })
  },

  /**
   * Calls POST /v1/auth/wechat/login with the wx.login code and user profile.
   * On success, persists tokens and navigates to the home page.
   */
  _wechatLogin(code, userInfo) {
    postNoAuth('/auth/wechat/login', {
      code,
      nickname: userInfo.nickName,
      avatar_url: userInfo.avatarUrl,
    })
      .then((res) => {
        // Persist access & refresh tokens
        saveTokens(res.access_token, res.refresh_token)

        // Cache user info
        wx.setStorageSync('user_info', {
          nickname: userInfo.nickName,
          avatar_url: userInfo.avatarUrl,
        })

        // Update app global state
        const app = getApp()
        app.globalData.userInfo = userInfo

        wx.showToast({ title: '登录成功', icon: 'success', duration: 1500 })

        // Redirect to home (replace so user cannot go back to login)
        setTimeout(() => {
          wx.reLaunch({ url: '/pages/home/index' })
        }, 1500)
      })
      .catch((err) => {
        this._onError(err.message || '登录失败，请重试')
      })
  },

  /**
   * Shared error handler: shows a toast and resets the login button.
   */
  _onError(msg) {
    this.setData({ isLogging: false })
    wx.showToast({ title: msg, icon: 'none', duration: 2000 })
  },
})
