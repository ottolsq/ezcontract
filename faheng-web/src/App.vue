<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const isFullscreen = computed(() => Boolean(route.meta.fullscreen))

async function onLogout() {
  await auth.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <header class="top-bar">
      <span class="brand" @click="router.push('/')">⚖️ 法衡 AI · 企业多智能体工作台</span>

      <nav v-if="auth.isLoggedIn" class="nav">
        <router-link to="/draft">合同起草</router-link>
        <router-link to="/review">合同审查</router-link>
      </nav>

      <div class="right-area">
        <template v-if="auth.isLoggedIn">
          <span class="user-chip">
            <span class="user-avatar">{{ auth.username.charAt(0).toUpperCase() }}</span>
            <span class="user-name">{{ auth.username }}</span>
          </span>
          <el-button text @click="onLogout">退出登录</el-button>
        </template>
        <el-button v-else type="primary" size="small" @click="router.push('/login')">
          登录
        </el-button>
      </div>
    </header>

    <main :class="['app-main', { 'app-main--full': isFullscreen }]">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.top-bar {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e4e9f2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  position: sticky;
  top: 0;
  z-index: 10;
}

.app-main {
  height: calc(100vh - 56px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 全屏路由（如 /login）：绕过固定高度，由子页面自己撑满剩余视口 */
.app-main--full {
  height: auto;
  min-height: calc(100vh - 56px);
  overflow: visible;
  display: block;
}

.brand {
  font-weight: 600;
  cursor: pointer;
}

.nav {
  display: flex;
  gap: 22px;
  margin-left: 32px;
  flex: 1;
}

.nav a {
  color: #66758a;
  text-decoration: none;
  font-size: 14px;
}

.nav a.router-link-active {
  color: #2459a9;
  font-weight: 600;
}

.right-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 4px 4px;
  background: #f0f4fa;
  border-radius: 999px;
  font-size: 13px;
  color: #1d2b4f;
}

.user-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #2459a9;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.user-name {
  font-weight: 500;
}
</style>
