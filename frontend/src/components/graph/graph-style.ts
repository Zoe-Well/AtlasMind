export const ENTITY_COLORS: Record<string, string> = {
  SYSTEM: "#5266d5",
  PRODUCT: "#7a5ccf",
  SERVICE: "#3f7fab",
  API: "#258f86",
  ERROR_CODE: "#c8645e",
  ORGANIZATION: "#b9743d",
  ORG_UNIT: "#b68e38",
  DATABASE: "#517ba3",
  QUEUE: "#896aaa",
  TECH_COMPONENT: "#5f8b67",
};

export const ENTITY_LABELS: Record<string, string> = {
  SYSTEM: "系统",
  PRODUCT: "产品",
  SERVICE: "服务",
  API: "接口",
  ERROR_CODE: "错误码",
  ORGANIZATION: "组织",
  ORG_UNIT: "组织单元",
  DATABASE: "数据库",
  QUEUE: "消息队列",
  TECH_COMPONENT: "技术组件",
};

export const DEFAULT_NODE_COLOR = "#777b88";
export const DEFAULT_EDGE_COLOR = "rgba(107, 116, 139, 0.17)";
export const MUTED_NODE_COLOR = "rgba(160, 164, 176, 0.22)";
export const MUTED_EDGE_COLOR = "rgba(170, 173, 185, 0.04)";
export const ACTIVE_EDGE_COLOR = "#5368d8";

export function entityColor(entityType: string) {
  return ENTITY_COLORS[entityType] ?? DEFAULT_NODE_COLOR;
}
