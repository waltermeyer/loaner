// Copyright 2018 Google Inc. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS-IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import {Injectable} from '@angular/core';
import {ActivatedRouteSnapshot, CanActivate, Router, RouterStateSnapshot} from '@angular/router';
import {Observable} from 'rxjs/Observable';
import {of} from 'rxjs/observable/of';
import {catchError, map} from 'rxjs/operators';

import {LoanerSnackBar} from './snackbar';
import {UserService} from './user';

@Injectable()
export class AuthGuard implements CanActivate {
  /** URL to navigate in case the user isn't authorized. */
  private authorizationUrl = 'authorization';

  constructor(
      private readonly snackbar: LoanerSnackBar,
      private router: Router,
      private userService: UserService,
  ) {}

  canActivate(route: ActivatedRouteSnapshot, state: RouterStateSnapshot) {
    const destinationUrl = state.url;
    return this.userService.loadUser().pipe(
        map(user => {
          const requiredRoles = route.data['requiredRoles'] as string[];
          const userCanAccess = isAllowedAccess(requiredRoles, user.roles);

          if (!userCanAccess) {
            if (destinationUrl.match(/^\/bootstrap/)) {
              const errorMessage =
                  `User ${user.email} is not allowed to setup the application.
                 Please contact your administator.`;
              this.snackbar.open(errorMessage, /* sticky notification */ true);
              throw new Error(errorMessage);
            } else {
              const errorMessage =
                  `User ${user.email} is not allowed to access page
                   ${destinationUrl}. Please contact your administator.`;
              this.snackbar.open(errorMessage);
              this.router.navigate(['/']);
            }
          }

          return userCanAccess;
        }),
        catchError(() => {
          this.router.navigate([this.authorizationUrl], {
            queryParams: {
              'returnUrl': destinationUrl,
            }
          });
          return of(false);
        }));
  }
}

/**
 * Return if whether a set of current roles intersects with the allowed roles.
 *
 * @param rolesAllowed Roles that are allowed access.
 * @param currentRoles Roles that the user currently has.
 */
const isAllowedAccess = (rolesAllowed: string[], currentRoles: string[]) => {
  const intersectedRoles = currentRoles.reduce(
      (acc, curr) =>
          [...acc,
           ...rolesAllowed.filter(
               role =>
                   role.trim().toUpperCase() === curr.trim().toUpperCase())],
      []);
  return intersectedRoles.length > 0;
};
