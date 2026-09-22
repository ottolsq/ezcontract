import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue') },
    {
      path: '/draft',
      name: 'draft',
      component: () => import('../views/DraftView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('../views/ReviewView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

// 全局守卫：未登录访问业务页 → 跳登录；已登录访问 /login → 跳首页
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && auth.isLoggedIn) {
    return { path: '/' }
  }
})

export default router
