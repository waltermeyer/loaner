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

import {ComponentFixture, ComponentFixtureAutoDetect, discardPeriodicTasks, fakeAsync, TestBed, tick,} from '@angular/core/testing';
import {BrowserAnimationsModule} from '@angular/platform-browser/animations';
import {RouterTestingModule} from '@angular/router/testing';
import {Shelf} from '../../models/shelf';
import {ShelfService} from '../../services/shelf';

import {ShelfServiceMock} from '../../testing/mocks';

import {ShelfListTable, ShelfListTableModule} from '.';


describe('ShelfListTableComponent', () => {
  let fixture: ComponentFixture<ShelfListTable>;
  let shelfListTable: ShelfListTable;

  beforeEach(fakeAsync(() => {
    TestBed
        .configureTestingModule({
          imports: [
            RouterTestingModule,
            ShelfListTableModule,
            BrowserAnimationsModule,
          ],
          providers: [
            {provide: ComponentFixtureAutoDetect, useValue: true},
            {provide: ShelfService, useClass: ShelfServiceMock},
          ],
        })
        .compileComponents();

    tick();

    fixture = TestBed.createComponent(ShelfListTable);
    shelfListTable = fixture.debugElement.componentInstance;

    discardPeriodicTasks();
  }));

  it('should create the ShelfList', () => {
    expect(shelfListTable).toBeDefined();
  });

  it('should render card title in a mat-card-title', () => {
    fixture.detectChanges();
    const compiled = fixture.debugElement.nativeElement;
    expect(compiled.querySelector('.mat-card-title').textContent)
        .toContain('Shelf List');
  });

  it('should render title field "Name" inside .mat-header-row ', () => {
    fixture.detectChanges();
    const compiled = fixture.debugElement.nativeElement;
    expect(compiled.querySelector('.mat-header-row').textContent)
        .toContain('Name');
  });

  it('should render title field "Capacity" inside .mat-header-row ', () => {
    fixture.detectChanges();
    const compiled = fixture.debugElement.nativeElement;
    expect(compiled.querySelector('.mat-header-row').textContent)
        .toContain('Capacity');
  });

  it('should render title field "Last Audit time" inside .mat-header-row ',
     () => {
       fixture.detectChanges();
       const compiled = fixture.debugElement.nativeElement;
       expect(compiled.querySelector('.mat-header-row').textContent)
           .toContain('Last Audit Time');
     });

  it('should render title field "Last Audit by" inside .mat-header-row ',
     () => {
       fixture.detectChanges();
       const compiled = fixture.debugElement.nativeElement;
       expect(compiled.querySelector('.mat-header-row').textContent)
           .toContain('Last Audit By');
     });

  it('should pause loading when a row has focus', () => {
    fixture.detectChanges();
    const compiled = fixture.debugElement.nativeElement;
    compiled.querySelector('.mat-row').dispatchEvent(new Event('focus'));
    fixture.detectChanges();
    expect(shelfListTable.pauseLoading).toBe(true);
  });
  it('should resume loading when a row loses focus', () => {
    fixture.detectChanges();
    const compiled = fixture.debugElement.nativeElement;
    const row: HTMLElement = compiled.querySelector('.mat-row');
    row.dispatchEvent(new Event('focus'));
    fixture.detectChanges();
    row.dispatchEvent(new Event('blur'));
    fixture.detectChanges();
    expect(shelfListTable.pauseLoading).toBe(false);
  });

  it('should pause loading when audit button has focus', () => {
    fixture.detectChanges();
    const compiled = fixture.debugElement.nativeElement;
    compiled.querySelector('.mat-cell > button')
        .dispatchEvent(new Event('focus'));
    expect(shelfListTable.pauseLoading).toBe(true);
  });

  it('should resume loading when audit button loses focus', () => {
    fixture.detectChanges();
    const compiled = fixture.debugElement.nativeElement;
    const auditButton: HTMLButtonElement =
        compiled.querySelector('.mat-cell > button');
    auditButton.focus();
    auditButton.blur();
    expect(shelfListTable.pauseLoading).toBe(false);
  });
});
