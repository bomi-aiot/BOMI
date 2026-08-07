"""pytest 가 이 폴더의 플랫 모듈(contract, mapping 등)을 import 할 수 있도록
해당 디렉터리를 sys.path 에 추가한다."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
