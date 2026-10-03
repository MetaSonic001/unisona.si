import {
  BarChart3, BookOpen, Bot, Building, Building2, Calendar, CheckSquare, ClipboardList, CreditCard, FlaskConical, Handshake, Home, Inbox,
  KanbanSquare, LayoutTemplate, Megaphone, PhoneCall, PlugZap, Radio, Settings, ShieldCheck, Star, Users, Workflow, type LucideIcon,
} from "lucide-react";

export type NavItem = { title: string; href: string; icon: LucideIcon; badge?: string };
export const NAV: { label?: string; items: NavItem[] }[] = [
  { items: [{ title: "Home", href: "/app", icon: Home }, { title: "Agents", href: "/app/agents", icon: Bot }, { title: "Inbox", href: "/app/inbox", icon: Inbox, badge: "inbox" }, { title: "Live", href: "/app/live", icon: Radio, badge: "live" }] },
  { label: "Customers", items: [{ title: "Contacts", href: "/app/crm/contacts", icon: Users }, { title: "Deals", href: "/app/crm/deals", icon: KanbanSquare }, { title: "Tasks", href: "/app/crm/tasks", icon: CheckSquare }, { title: "Calendar", href: "/app/crm/calendar", icon: Calendar }, { title: "Companies", href: "/app/crm/companies", icon: Building2 }] },
  { label: "Grow", items: [{ title: "Campaigns", href: "/app/campaigns", icon: Megaphone }, { title: "Automations", href: "/app/automations", icon: Workflow }, { title: "Calls", href: "/app/calls", icon: PhoneCall },
    { title: "Forms & surveys", href: "/app/forms", icon: ClipboardList }, { title: "Sites", href: "/app/sites", icon: LayoutTemplate }, { title: "Reputation", href: "/app/reputation", icon: Star },
    { title: "Payments", href: "/app/payments", icon: CreditCard }] },
  { label: "Build", items: [{ title: "Knowledge", href: "/app/knowledge", icon: BookOpen }, { title: "Evaluations", href: "/app/evals", icon: FlaskConical }, { title: "Integrations", href: "/app/integrations", icon: PlugZap }, { title: "Analytics", href: "/app/analytics", icon: BarChart3 }] },
  { items: [{ title: "Compliance", href: "/app/compliance", icon: ShieldCheck }, { title: "Agency", href: "/app/agency", icon: Building }, { title: "Settings", href: "/app/settings", icon: Settings }] },
];
export const HANDOFF_ICON = Handshake;
