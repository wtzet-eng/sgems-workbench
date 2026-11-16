// Standalone ordinary kriging worker. Input: range, sample count, target count,
// then XYZ/value sample rows and XYZ target rows. Output: estimate and variance
// for a unit-sill spherical covariance with zero nugget.
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <vector>
#include <GsTL/kriging/kriging_weights.h>
#include <GsTL/kriging/OK_constraints.h>

#include "spatial.h"
int main() {
    Spherical covariance;
    int n, m;
    if (!(std::cin >> covariance.range >> n >> m) || covariance.range <= 0 || n < 1 || m < 1)
        return 1;
    Neighbours samples;
    for (int i=0; i<n; ++i) {
        Sample s;
        if (!(std::cin >> s.position.x >> s.position.y >> s.position.z >> s.value)) return 1;
        samples.push_back(s);
    }
    std::cout << std::setprecision(17);
    OK_constraints constraints;
    for (int i=0; i<m; ++i) {
        Point target;
        if (!(std::cin >> target.x >> target.y >> target.z)) return 1;
        auto end = samples.begin() + std::min(n,16);
        std::partial_sort(samples.begin(),end,samples.end(),[&](const Sample& a,const Sample& b){
            double da=distance(a.position,target), db=distance(b.position,target);
            if (da!=db) return da<db;
            if (a.position.x!=b.position.x) return a.position.x<b.position.x;
            if (a.position.y!=b.position.y) return a.position.y<b.position.y;
            return a.position.z<b.position.z;
        });
        if (distance(samples.front().position,target)==0) {
            std::cout << samples.front().value << " 0\n";
            continue;
        }
        Neighbours local;
        local.assign(samples.begin(),end);
        std::vector<double> weights;
        double variance=0;
        if (kriging_weights(weights,variance,target,local,covariance,constraints)!=0) return 2;
        double estimate=0;
        for (size_t j=0; j<local.size(); ++j) estimate+=weights[j]*local[j].value;
        std::cout << estimate << " " << variance << "\n";
    }
}
