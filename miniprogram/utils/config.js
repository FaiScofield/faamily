/** API 配置常量 */
const CONFIG = {
  // 开发环境：用本地地址；生产环境替换为线上地址
  BASE_URL: 'http://localhost:8000/v1',

  // Token 在 Storage 中的 key
  ACCESS_TOKEN_KEY: 'access_token',
  REFRESH_TOKEN_KEY: 'refresh_token',
  USER_INFO_KEY: 'user_info',
}

export default CONFIG
