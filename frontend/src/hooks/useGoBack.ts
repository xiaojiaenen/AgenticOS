/**
 * 统一的「返回」语义。
 *
 * 直接 `navigate(-1)` 在两种情况下会出错：用户是从新标签页直接打开的
 * （history.length === 1，会退到 about:blank 或什么都不发生），或者是从
 * 外链跳进来。写死 `navigate('/')` 更糟 —— 用户从 /chat 进 /agents 点返回
 * 被扔回首页，等于丢掉来路。
 *
 * 规则：有可回退的历史就 back()（回到来路），否则落到该页声明的语义父页。
 * 用 react-router 的 location.key 判断：首次渲染的 key 是 "default"，
 * 说明这是本次会话的第一个 entry，没有来路可退。
 */
import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export function useGoBack(fallback = '/chat') {
  const navigate = useNavigate();
  const location = useLocation();

  return useCallback(() => {
    // "default" = 本会话的第一个 location，没有来路
    const isFirstEntry = location.key === 'default';
    if (!isFirstEntry) {
      navigate(-1);
      return;
    }
    navigate(fallback, { replace: true });
  }, [navigate, location.key, fallback]);
}
