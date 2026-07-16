export type FeatureUsagePoint = { day: string; feature: string; count: number; credits: number };
export type FeatureUsageTotal = { feature: string; count: number; credits: number; share?: number };
export type UserGrowthPoint = { day: string; new_users: number; cumulative_users: number };
export type HighFrequencyUsagePoint = { day: string; count: number; credits: number };

export type RecentUsageEvent = {
  id: number;
  user_id: number;
  username?: string;
  email?: string;
  phone?: string;
  display_name: string;
  feature: string;
  credits_spent: number;
  status: string;
  related_id?: string;
  used_at: string;
  market_session?: "before_open" | "after_open" | null;
};

export type HighFrequencyUser = {
  id: number;
  phone?: string;
  username?: string;
  email?: string;
  total_uses: number;
  credits_spent: number;
  active_days: number;
  usage_by_day: HighFrequencyUsagePoint[];
};

export type AdminAnalytics = {
  window?: { days: number; start_date: string; end_date: string };
  feature_usage?: {
    totals?: FeatureUsageTotal[];
    by_day?: FeatureUsagePoint[];
  };
  user_growth?: {
    starting_users?: number;
    total_users?: number;
    by_day?: Array<Partial<UserGrowthPoint> & { day: string; count?: number; total_users?: number }>;
  };
  high_frequency_users?: Array<{
    id?: number;
    phone?: string;
    username?: string;
    email?: string;
    total_uses?: number;
    credits_spent?: number;
    active_days?: number;
    usage_by_day?: Array<Partial<HighFrequencyUsagePoint> & { day: string }>;
  }>;
  recent_usage_events?: RecentUsageEvent[];
};
