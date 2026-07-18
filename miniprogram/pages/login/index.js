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
  onLogin() {
    if (this.data.isLogging) return
    this.setData({ isLogging: true })
    wx.login({
      success: (loginRes) => {
        if (!loginRes.code) {
          this._onError('wx.login failed')
          return
        }
        this._wechatLogin(loginRes.code)
      },
      fail: () => {
        this._onError('wx.login failed')
      },
    })
  },

  /**
   * Calls POST /v1/auth/wechat/login with the wx.login code and user profile.
   * On success, persists tokens and navigates to the home page.
   */
  _wechatLogin(code) {
    postNoAuth('/auth/wechat/login', { code })
      .then((res) => {
        saveTokens(res.access_token, res.refresh_token)
        wx.setStorageSync('user_info', { id: res.user_id, user_id: res.user_id })
        wx.showToast({ title: 'logged in', icon: 'success', duration: 1500 })
        setTimeout(() => { wx.reLaunch({ url: '/pages/home/index' }) }, 1500)
      })
      .catch((err) => {
        this._onError(err.message || 'login failed')
      })
  },

  onGuestLogin() {
    if (this.data.isLogging) return
    this.setData({ isLogging: true })
    postNoAuth('/auth/guest')
      .then((res) => {
        saveTokens(res.access_token, res.refresh_token)
        wx.setStorageSync('user_info', { id: res.user_id, user_id: res.user_id })
        wx.reLaunch({ url: '/pages/home/index' })
      })
      .catch((err) => {
        this._onError(err.message || 'guest login failed')
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
