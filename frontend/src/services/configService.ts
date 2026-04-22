export type AppConfig = {
  enableLaTeX: boolean;
  enableMermaid: boolean;
  enableSearch: boolean;
  enableArtifacts: boolean;
};

const DEFAULT_CONFIG: AppConfig = {
  enableLaTeX: true,
  enableMermaid: true,
  enableSearch: true,
  enableArtifacts: true,
};

export const getAppConfig = (): AppConfig => {
  const saved = localStorage.getItem('app_config');
  if (!saved) return DEFAULT_CONFIG;
  try {
    return { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
  } catch {
    return DEFAULT_CONFIG;
  }
};

export const saveAppConfig = (config: AppConfig) => {
  localStorage.setItem('app_config', JSON.stringify(config));
};
