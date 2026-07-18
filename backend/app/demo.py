from .domain import League, Player, Team


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
    agents = [p("fa1", "Rico Dowdle", "RB", "CAR", 11.8, 5.3, rostered=False), p("fa2", "Josh Downs", "WR", "IND", 13.4, 5.1, rostered=False), p("fa3", "Hunter Henry", "TE", "NE", 9.8, 4.2, rostered=False)]
    return League(id="demo", name="The Sunday League", season=2026, week=11, user_team_id="1", roster_slots=["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DST"], teams=[user, opp], free_agents=agents)
