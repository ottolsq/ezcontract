<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="app-shell">
    <header class="top-bar">
      <span class="brand" @click="router.push('/')">⚖️ 法衡 AI · 企业多智能体工作台</span>
      <nav class="nav">
        <router-link to="/draft">合同起草</router-link>
        <router-link to="/review">合同审查</router-link>
      </nav>
    </header>
    <main class="app-main">
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
  min-height: calc(100vh - 56px);
}

.brand {
  font-weight: 600;
  cursor: pointer;
}

.nav {
  display: flex;
  gap: 22px;
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
</style>
