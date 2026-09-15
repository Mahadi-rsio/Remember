export type LogLevel = "debug" | "info" | "warn" | "error" | "silent";

const ORDER: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
  silent: 999,
};

let currentLevel: LogLevel = "info";

export function configureLogLevel(level: LogLevel | string | undefined): void {
  if (level && level in ORDER) {
    currentLevel = level as LogLevel;
  }
}

function emit(level: LogLevel, stage: string, msg: string, data?: Record<string, unknown>): void {
  if (ORDER[level] < ORDER[currentLevel]) return;
  const line = `[pipeline:${stage}] ${msg}`;
  if (data && Object.keys(data).length > 0) {
    console.log(line, JSON.stringify(data));
  } else {
    console.log(line);
  }
}

export const debug = (stage: string, msg: string, data?: Record<string, unknown>) =>
  emit("debug", stage, msg, data);
export const info = (stage: string, msg: string, data?: Record<string, unknown>) =>
  emit("info", stage, msg, data);
export const warn = (stage: string, msg: string, data?: Record<string, unknown>) =>
  emit("warn", stage, msg, data);
export const error = (stage: string, msg: string, data?: Record<string, unknown>) =>
  emit("error", stage, msg, data);
