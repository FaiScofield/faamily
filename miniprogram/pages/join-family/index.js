import { post } from '../../utils/api'

Page({
  data: {
    inviteCode: '',
    submitting: false,
  },

  onCodeInput(e) {
    this.setData({ inviteCode: e.detail.value })
  },

  onSubmit() {
    if (this.data.submitting) return
    const code = (this.data.inviteCode || '').trim().toUpperCase()
    if (!code) {
      wx.showToast({ title: '请输入邀请码', icon: 'none' })
      return
    }
    if (code.length < 6) {
      wx.showToast({ title: '邀请码格式不正确', icon: 'none' })
      return
    }

    this.setData({ submitting: true })
    post('/families/join', { code })
      .then((res) => {
        const app = getApp()
        app.globalData.currentFamilyId = res.family_id
        wx.showToast({ title: '加入成功', icon: 'success', duration: 1500 })
        setTimeout(() => {
          wx.switchTab({ url: '/pages/home/index' })
        }, 1500)
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加入失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ submitting: false })
      })
  },
})
