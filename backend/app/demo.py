from .domain import League, LeagueRuleSet, Matchup, Player, Team


def p(pid: str, name: str, pos: str, team: str, mean: float, sd: float, *, rostered: bool = True, injury: str = "HEALTHY") -> Player:
    slots = {pos}
    if pos in {"RB", "WR", "TE"}: slots.add("FLEX")
    return Player(id=pid, name=name, position=pos, team=team, eligible_slots=slots, mean=mean, stdev=sd, rostered=rostered, injury_status=injury, availability=.78 if injury == "QUESTIONABLE" else 1)


def demo_league() -> League:
    user = Team(id="1", name="Sunday Algorithms", record="7-3", players=[
        p("q1", "Lamar Jackson", "QB", "BAL", 23.8, 6.1), p("r1", "Bijan Robinson", "RB", "ATL", 18.9, 5.2),
        p("r2", "Breece Hall", "RB", "NYJ", 15.7, 5.8), p("w1", "Amon-Ra St. Brown", "WR", "DET", 19.3, 4.8),
        p("w2", "Drake London", "WR", "ATL", 15.1, 5.0), p("t1", "Trey McBride", "TE", "ARI", 14.0, 4.2),
        p("w3", "Jaylen Waddle", "WR", "MIA", 12.8, 5.8, injury="QUESTIONABLE"), p("k1", "Jake Elliott", "K", "PHI", 8.2, 3.1),
        p("d1", "Steelers D/ST", "DST", "PIT", 8.5, 4.5), p("b1", "Jordan Addison", "WR", "MIN", 12.2, 5.4),
        p("b2", "Tyjae Spears", "RB", "TEN", 9.4, 4.8), p("b3", "Brock Purdy", "QB", "SF", 18.1, 4.7),
    ])
    opp = Team(id="2", name="Gridiron Theory", record="6-4", players=[
        p("oq", "Jalen Hurts", "QB", "PHI", 22.1, 6), p("or", "Saquon Barkley", "RB", "PHI", 19.4, 5),
        p("or2", "James Cook", "RB", "BUF", 15.9, 4.9), p("ow1", "CeeDee Lamb", "WR", "DAL", 18.6, 5.6),
        p("ow2", "DeVonta Smith", "WR", "PHI", 13.7, 5.1), p("ot", "Sam LaPorta", "TE", "DET", 11.9, 4.3),
        p("of", "George Pickens", "WR", "DAL", 14.4, 5.9), p("ok", "Brandon Aubrey", "K", "DAL", 9.1, 3.2),
        p("od", "Eagles D/ST", "DST", "PHI", 8.1, 4.1), p("ob1", "Jayden Reed", "WR", "GB", 10.8, 5.5),
        p("ob2", "Zach Charbonnet", "RB", "SEA", 9.7, 5.1), p("ob3", "Dak Prescott", "QB", "DAL", 17.4, 5.0),
    ])
    third = Team(id="3", name="Red Zone Models", record="5-5", players=[
        p("t3q", "Joe Burrow", "QB", "CIN", 21.6, 5.7), p("t3r1", "Jahmyr Gibbs", "RB", "DET", 17.8, 5.4),
        p("t3r2", "Kenneth Walker III", "RB", "SEA", 14.2, 5.0), p("t3w1", "Puka Nacua", "WR", "LAR", 18.0, 5.1),
        p("t3w2", "DJ Moore", "WR", "CHI", 13.9, 5.7), p("t3t", "George Kittle", "TE", "SF", 12.4, 4.9),
        p("t3f", "Chris Godwin", "WR", "TB", 12.7, 4.8), p("t3k", "Younghoe Koo", "K", "ATL", 8.0, 3.2),
        p("t3d", "Ravens D/ST", "DST", "BAL", 8.8, 4.6),
    ])
    fourth = Team(id="4", name="Two Minute Drill", record="4-6", players=[
        p("t4q", "Justin Herbert", "QB", "LAC", 20.7, 5.4), p("t4r1", "Jonathan Taylor", "RB", "IND", 16.5, 5.6),
        p("t4r2", "Rachaad White", "RB", "TB", 13.2, 4.9), p("t4w1", "Nico Collins", "WR", "HOU", 17.2, 5.5),
        p("t4w2", "Terry McLaurin", "WR", "WAS", 12.9, 5.0), p("t4t", "Jake Ferguson", "TE", "DAL", 10.8, 4.3),
        p("t4f", "Rome Odunze", "WR", "CHI", 10.9, 5.2), p("t4k", "Jason Sanders", "K", "MIA", 7.8, 3.1),
        p("t4d", "Bills D/ST", "DST", "BUF", 8.3, 4.2),
    ])
    teams = [user, opp, third, fourth]
    for team, wins, losses, pf, pa in [
        (user, 7, 3, 1198.4, 1116.2),
        (opp, 6, 4, 1164.1, 1122.6),
        (third, 5, 5, 1130.5, 1142.7),
        (fourth, 4, 6, 1105.8, 1217.3),
    ]:
        team.wins = wins
        team.losses = losses
        team.points_for = pf
        team.points_against = pa
    schedule = [
        Matchup(id="1-1-2", period=1, home_team_id="1", away_team_id="2", home_score=121.4, away_score=112.7, is_complete=True),
        Matchup(id="1-3-4", period=1, home_team_id="3", away_team_id="4", home_score=106.2, away_score=109.1, is_complete=True),
        Matchup(id="2-1-3", period=2, home_team_id="1", away_team_id="3", home_score=99.8, away_score=111.3, is_complete=True),
        Matchup(id="2-2-4", period=2, home_team_id="2", away_team_id="4", home_score=118.4, away_score=105.9, is_complete=True),
        Matchup(id="3-1-4", period=3, home_team_id="1", away_team_id="4", home_score=117.0, away_score=103.6, is_complete=True),
        Matchup(id="3-2-3", period=3, home_team_id="2", away_team_id="3", home_score=108.4, away_score=114.2, is_complete=True),
        Matchup(id="11-1-2", period=11, home_team_id="1", away_team_id="2", is_current=True),
        Matchup(id="11-3-4", period=11, home_team_id="3", away_team_id="4", is_current=True),
        Matchup(id="12-1-3", period=12, home_team_id="1", away_team_id="3"),
        Matchup(id="12-2-4", period=12, home_team_id="2", away_team_id="4"),
        Matchup(id="13-1-4", period=13, home_team_id="1", away_team_id="4"),
        Matchup(id="13-2-3", period=13, home_team_id="2", away_team_id="3"),
        Matchup(id="14-1-2", period=14, home_team_id="1", away_team_id="2"),
        Matchup(id="14-3-4", period=14, home_team_id="3", away_team_id="4"),
    ]
    agents = [p("fa1", "Rico Dowdle", "RB", "CAR", 11.8, 5.3, rostered=False), p("fa2", "Josh Downs", "WR", "IND", 13.4, 5.1, rostered=False), p("fa3", "Hunter Henry", "TE", "NE", 9.8, 4.2, rostered=False)]
    rules = LeagueRuleSet(regular_season_start=1, regular_season_end=14, playoff_start=15, playoff_end=16, first_round_byes=0, tiebreaker="record_then_points_for", assumptions=["Demo schedule is synthetic and visibly labeled; it exists only to exercise Phase 4 workflows."])
    return League(id="demo", name="The Sunday League", season=2026, week=11, user_team_id="1", roster_slots=["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DST"], teams=teams, free_agents=agents, playoff_team_count=4, rules=rules, schedule=schedule)
