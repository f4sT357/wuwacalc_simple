
from constants import CHARACTER_STAT_WEIGHTS
from echo_data import EchoData


def get_rating(score):
    if score >= 100:
        return "SSS"
    elif score >= 90:
        return "SS"
    elif score >= 80:
        return "S"
    elif score >= 70:
        return "A"
    elif score >= 60:
        return "B"
    else:
        return "C"


def run_demo():
    # Test Case: Theoretical Max Echo
    max_substats = {
        "クリティカル率": 10.5,
        "クリティカルダメージ": 21.0,
        "攻撃力%": 11.6,
        "攻撃力": 60,
        "共鳴効率": 12.4
    }
    weights = CHARACTER_STAT_WEIGHTS["General"]

    echo = EchoData(4, "クリティカル率", max_substats)
    score = echo.calculate_score(weights)
    norm_score = echo.calculate_score_normalized(weights)
    roll_score = echo.calculate_score_roll_quality(weights)

    print(f"Standard Score: {score}")
    print(f"Normalized Score: {norm_score}")
    print(f"Roll Quality Score: {roll_score}")

    print(f"Rating: {get_rating(score)}")
    print(f"Normalized Rating: {echo.get_rating_normalized(norm_score)}")
    print(f"Roll Rating: {echo.get_rating_roll(roll_score)}")


if __name__ == '__main__':
    run_demo()

