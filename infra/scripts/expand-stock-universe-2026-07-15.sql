-- Stock universe expansion: top liquid NSE names by MEASURED median daily
-- traded value (>= Rs25.0cr/day, price Rs20.0-Rs4000.0), 6mo window.
-- Adds Stock rows ONLY. Creates no ActiveConfiguration, so nothing goes live
-- and no money is at risk; it widens the BACKTEST universe (better statistics
-- than best-of-19 cherry-picking). Idempotent.
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('ICICIBANK', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs2147.1 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('RELIANCE', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs2096.3 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('SBIN', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs1509.0 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('TCS', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs904.5 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('MCX', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs891.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('LT', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs882.4 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('M&M', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs843.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('AXISBANK', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs813.4 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('BAJFINANCE', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs759.4 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('KOTAKBANK', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs621.4 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('SHRIRAMFIN', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs572.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('BEL', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs560.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('TATASTEEL', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs546.9 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('HINDALCO', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs524.6 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('ITC', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs516.7 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('SUNPHARMA', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs450.7 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('KAYNES', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs442.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('NTPC', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs410.9 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('ONGC', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs406.4 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('HCLTECH', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs396.7 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('NATIONALUM', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs388.9 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('COALINDIA', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs386.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('BHEL', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs378.3 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('HINDCOPPER', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs376.9 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('COFORGE', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs375.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('TMCV', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs371.8 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('WIPRO', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs369.7 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('HINDUNILVR', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs358.9 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('TMPV', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs356.0 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('ADANIGREEN', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs348.5 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('SAIL', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs343.4 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('ASHOKLEY', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs341.8 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('POWERGRID', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs337.5 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('JIOFIN', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs334.8 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('SUZLON', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs331.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('CANBK', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs331.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('TRENT', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs319.6 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('WAAREEENER', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs319.2 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('TVSMOTOR', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs308.4 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('BPCL', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs306.3 cr/day
INSERT INTO "Stock" (symbol, "isActive", "createdAt") VALUES ('HINDZINC', true, NOW()) ON CONFLICT (symbol) DO NOTHING;  -- Rs301.5 cr/day
