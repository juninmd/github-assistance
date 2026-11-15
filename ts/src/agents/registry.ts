/** Agent registry. Ported agents register a loader here; the rest fail loudly (Python still owns them). */
import type { Settings } from "../config/settings.ts";
import { AGENTS_BY_NAME } from "./catalog.ts";

export type AgentContext = { settings: Settings; provider?: string; model?: string; prRef?: string };
export interface Agent { run(): Promise<Record<string, any>> }
export type AgentLoader = (ctx: AgentContext) => Promise<Agent>;

/** name -> lazy loader. Add an entry when an agent is ported. */
export const PORTED: Record<string, AgentLoader> = {};

export const registeredNames = () => [...AGENTS_BY_NAME.keys()];

export async function createAgent(name: string, ctx: AgentContext): Promise<Agent> {
  if (!AGENTS_BY_NAME.has(name)) throw new Error(`unknown agent: ${name}`);
  const loader = PORTED[name];
  if (!loader) throw new Error(`agent '${name}' ainda não foi portado para Bun (veja o quadro de paridade no README)`);
  return loader(ctx);
}
