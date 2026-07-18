import { post } from '../../utils/api'

Page({
  data: {
    familyName: '',
    submitting: false,
  },

  onNameInput(e) {
    this.setData({ familyName: e.detail.value })
  },

  onSubmit() {
    if (this.data.submitting) return
    const name = (this.data.familyName || '').trim()
    if (!name) {
      wx.showToast({ title: '请输入家庭名称', icon: 'none' })
      return
    }

    this.setData({ submitting: true })
    post('/families', { name })
      .then((res) => {
        const app = getApp()
        app.globalData.currentFamilyId = res.family_id
        wx.showToast({ title: '创建成功', icon: 'success', duration: 1500 })
        setTimeout(() => {
          wx.switchTab({ url: '/pages/home/index' })
        }, 1500)
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '创建失败', icon: 'none' })
      })
      .finally(() => {
        this.setData({ submitting: false })
      })
  },
})
