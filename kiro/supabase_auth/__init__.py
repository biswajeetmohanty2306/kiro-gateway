# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Phase C — Supabase downstream user-auth validation (backend resource server).

This package verifies the identity of OUR application's users on each request
(user JWT issued by Supabase Auth). It is entirely separate from the UPSTREAM
Kiro/AWS authentication in ``kiro/auth.py`` — a user JWT never reaches the
Kiro API.

Milestone M0 (this commit) provides configuration only:
  - ``config``: validated, lazily-built configuration object.

Verification, dependencies, DB access, routes, and middleware arrive in later
milestones (M1–M7) per ``docs/architecture/PhaseCImplementationPlan.md``.
"""
