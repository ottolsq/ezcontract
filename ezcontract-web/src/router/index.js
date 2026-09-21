import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue') },
    { path: '/draft', name: 'draft', component: () => import('../views/DraftView.vue') },
    { path: '/review', name: 'review', component: () => import('../views/ReviewView.vue') },
  ],
})

export default router
