/**
 * HTTP 请求封装
 * 自动处理 JWT token 注入、401 自动刷新、错误统一处理
 */
import CONFIG from './config'

// 是否正在刷新 token 的锁，防止并发刷新
let isRefreshing = false
let pendingRequests = []

function getToken() {
  return wx.getStorageSync(CONFIG.ACCESS_TOKEN_KEY) || ''
}

function getRefreshToken() {
  return wx.getStorageSync(CONFIG.REFRESH_TOKEN_KEY) || ''
}

function saveTokens(accessToken, refreshToken) {
  wx.setStorageSync(CONFIG.ACCESS_TOKEN_KEY, accessToken)
  wx.setStorageSync(CONFIG.REFRESH_TOKEN_KEY, refreshToken)
}

function clearTokens() {
  wx.removeStorageSync(CONFIG.ACCESS_TOKEN_KEY)
  wx.removeStorageSync(CONFIG.REFRESH_TOKEN_KEY)
  wx.removeStorageSync(CONFIG.USER_INFO_KEY)
}

/**
 * 刷新 access token
 */
function refreshAccessToken() {
  return new Promise((resolve, reject) => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) {
      reject(new Error('No refresh token'))
      return
    }
    wx.request({
      url: `${CONFIG.BASE_URL}/auth/refresh`,
      method: 'POST',
      data: { refresh_token: refreshToken },
      success: (res) => {
        if (res.data && res.data.access_token) {
          saveTokens(res.data.access_token, res.data.refresh_token)
          resolve(res.data.access_token)
        } else {
          reject(new Error('Refresh failed'))
        }
      },
      fail: reject,
    })
  })
}

/**
 * 核心请求方法
 * @param {string} url    相对路径，如 /auth/me
 * @param {object} options  { method, data, noAuth }
 */
function request(url, options = {}) {
  const { method = 'GET', data, noAuth = false } = options

  return new Promise((resolve, reject) => {
    const header = { 'Content-Type': 'application/json' }

    // 自动注入 token
    if (!noAuth) {
      const token = getToken()
      if (token) {
        header['Authorization'] = `Bearer ${token}`
      }
    }

    const doRequest = () => {
      wx.request({
        url: `${CONFIG.BASE_URL}${url}`,
        method,
        header,
        data,
        success: (res) => {
          if (res.statusCode === 401 && !noAuth) {
            // Token 过期，尝试刷新
            if (isRefreshing) {
              // 排队等待刷新完成
              pendingRequests.push({ resolve, reject, url, options })
              return
            }
            isRefreshing = true
            refreshAccessToken()
              .then((newToken) => {
                isRefreshing = false
                header['Authorization'] = `Bearer ${newToken}`
                // 重试当前请求
                wx.request({
                  url: `${CONFIG.BASE_URL}${url}`,
                  method,
                  header,
                  data,
                  success: (r) => resolve(r.data),
                  fail: reject,
                })
                // 处理排队的请求
                pendingRequests.forEach((p) => {
                  p.resolve(request(p.url, p.options))
                })
                pendingRequests = []
              })
              .catch(() => {
                isRefreshing = false
                pendingRequests = []
                clearTokens()
                // 跳转到登录页
                wx.redirectTo({ url: '/pages/login/index' })
                reject(new Error('Session expired'))
              })
          } else if (res.statusCode >= 400) {
            // 业务错误
            const msg = res.data?.detail || res.data?.message || `请求失败(${res.statusCode})`
            reject({ code: res.statusCode, message: msg, data: res.data })
          } else {
            resolve(res.data)
          }
        },
        fail: () => {
          reject({ code: -1, message: '网络异常，请检查网络连接' })
        },
      })
    }

    doRequest()
  })
}

/** GET 请求 */
export function get(url, params) {
  return request(url, { method: 'GET', data: params })
}

/** POST 请求 */
export function post(url, data) {
  return request(url, { method: 'POST', data })
}

/** PUT 请求 */
export function put(url, data) {
  return request(url, { method: 'PUT', data })
}

/** DELETE 请求 */
export function del(url) {
  return request(url, { method: 'DELETE' })
}

/** 无需 token 的请求（登录、注册等） */
export function postNoAuth(url, data) {
  return request(url, { method: 'POST', data, noAuth: true })
}

export { clearTokens, saveTokens, getToken }
